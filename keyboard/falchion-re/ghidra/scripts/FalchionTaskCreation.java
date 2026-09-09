// Recover RTOS task creation from the instruction stream.
//
// Two read-only modes, either or both per run:
//   validate=0xa,0xb,...   report whether each address is a valid Thumb
//                          subroutine start, without creating anything
//   primitive=0xaddr       find every call to that function and resolve the
//                          arguments at each call site
//
// Arguments are resolved by Ghidra's constant propagation over the CALLING
// function, not by reading nearby bytes. r0-r3 are read directly at the call
// instruction. Arguments five and six live on the stack under AAPCS, so for
// those the script scans backwards inside the calling function for the last
// `str <reg>,[sp,#off]` at that offset and resolves <reg> at the store. An
// argument that cannot be resolved that way is emitted as `unknown` and
// counted; it is never guessed, and a call site with any unknown argument is
// reported in full rather than dropped.
//
// Output lines:
//   PRIMITIVE entry=<addr> name=<n> params=<n> body=<lo>..<hi> callers=<n>
//   CALLSITE primitive=<addr> instr=<addr> func=<entry> order=<n>
//            a0=<v|unknown> a1=<v|unknown> a2=<v|unknown> a3=<v|unknown>
//            a4=<v|unknown> a5=<v|unknown> str=<ascii|none>
//   TARGET addr=<a> thumb=<bool> mapped=<bool> valid_subroutine=<bool>
//          defined=<bool> at=<name|none>
//   RESULT callsites=<n> resolved=<n> partial=<n> validated=<n>
//
// @category Falchion
import ghidra.app.plugin.core.analysis.ConstantPropagationContextEvaluator;
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.util.SymbolicPropogator;
import ghidra.program.util.SymbolicPropogator.Value;

import java.util.ArrayList;
import java.util.List;

public class FalchionTaskCreation extends GhidraScript {

    private static final String[] ARG_REGISTERS = {"r0", "r1", "r2", "r3"};
    // Stack slots for arguments five and six under AAPCS.
    private static final int[] STACK_SLOTS = {0, 4};
    private static final int MAX_STRING = 48;

    private Address addr(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
            .getAddress(value);
    }

    private boolean mapped(long value) {
        try {
            return currentProgram.getMemory().contains(addr(value));
        } catch (Exception exception) {
            return false;
        }
    }

    /** ASCII at `value`, or null when it is not a plausible string pointer. */
    private String stringAt(long value) {
        if (!mapped(value)) {
            return null;
        }
        StringBuilder out = new StringBuilder();
        try {
            Address cursor = addr(value);
            for (int index = 0; index < MAX_STRING; index++) {
                int byteValue = currentProgram.getMemory().getByte(cursor) & 0xff;
                if (byteValue == 0) {
                    return out.length() > 0 ? out.toString() : null;
                }
                if (byteValue < 0x20 || byteValue > 0x7e) {
                    return null;
                }
                out.append((char) byteValue);
                cursor = cursor.add(1);
            }
        } catch (Exception exception) {
            return null;
        }
        return null;
    }

    private String show(Value value) {
        if (value == null) {
            return "unknown";
        }
        return "0x" + Long.toHexString(value.getValue() & 0xffffffffL);
    }

    /**
     * Resolve the value stored to [sp,#slot] by the last such store before
     * `call` inside `function`. Returns null when there is no such store or
     * when the stored register's value is not known there.
     */
    private Value stackArgument(SymbolicPropogator propagator, Function function,
            Instruction call, int slot) {
        Listing listing = currentProgram.getListing();
        InstructionIterator instructions =
            listing.getInstructions(function.getBody(), true);
        Instruction best = null;
        Register stored = null;
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            if (instruction.getAddress().compareTo(call.getAddress()) >= 0) {
                break;
            }
            if (!instruction.getMnemonicString().toLowerCase().startsWith("str")) {
                continue;
            }
            if (instruction.getNumOperands() < 2) {
                continue;
            }
            Register base = null;
            long offset = 0;
            int memoryOperand = instruction.getNumOperands() - 1;
            for (Object part : instruction.getOpObjects(memoryOperand)) {
                if (part instanceof Register) {
                    base = (Register) part;
                } else if (part instanceof Scalar) {
                    offset = ((Scalar) part).getSignedValue();
                }
            }
            if (base == null || !base.getName().equalsIgnoreCase("sp")) {
                continue;
            }
            boolean isDouble = instruction.getMnemonicString().toLowerCase()
                .startsWith("strd");
            if (offset != slot && !(isDouble && offset == slot - 4
                    && instruction.getNumOperands() >= 3)) {
                continue;
            }
            // `strd Ra,Rb,[sp,#k]` writes Ra at k and Rb at k+4, so a slot
            // reached only by the second half of a strd is resolvable too.
            // Ignoring it would report a resolvable argument as unknown.
            int which = (offset == slot) ? 0 : 1;
            Object[] source = instruction.getOpObjects(which);
            if (source.length != 1 || !(source[0] instanceof Register)) {
                continue;
            }
            best = instruction;
            stored = (Register) source[0];
        }
        if (best == null || stored == null) {
            return null;
        }
        return propagator.getRegisterValue(best.getAddress(), stored);
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        println("PROGRAM " + currentProgram.getName());
        List<Long> validate = new ArrayList<>();
        List<Long> primitives = new ArrayList<>();
        boolean indirect = false;
        for (String argument : args) {
            int split = argument.indexOf('=');
            if (split <= 0) {
                println("SKIP " + argument + " reason=not_a_key_equals_value");
                continue;
            }
            String key = argument.substring(0, split);
            if (key.equals("indirect")) {
                indirect = !argument.substring(split + 1).equals("0");
                continue;
            }
            for (String item : argument.substring(split + 1).split(",")) {
                String text = item.trim().replaceFirst("^0[xX]", "");
                if (text.isEmpty()) {
                    continue;
                }
                long value = Long.parseLong(text, 16);
                if (key.equals("validate")) {
                    validate.add(value);
                } else if (key.equals("primitive")) {
                    primitives.add(value);
                } else {
                    println("SKIP " + argument + " reason=unknown_key");
                }
            }
        }

        PseudoDisassembler pseudo = new PseudoDisassembler(currentProgram);
        int validated = 0;
        for (long value : validate) {
            long target = value & ~1L;
            boolean thumb = (value & 1L) == 1L;
            boolean isMapped = mapped(target);
            boolean valid = false;
            if (isMapped) {
                try {
                    valid = pseudo.isValidSubroutine(addr(target));
                } catch (Exception exception) {
                    valid = false;
                }
            }
            Function existing = isMapped ? getFunctionAt(addr(target)) : null;
            // isValidSubroutine is a heuristic and returns false for a span
            // that is still undefined data, which every unseeded target is.
            // Decoding forward from the address says whether the bytes are
            // Thumb at all, so both are reported and neither is hidden.
            int decoded = 0;
            String prologue = "none";
            if (isMapped) {
                Address cursor = addr(target);
                for (int step = 0; step < 8; step++) {
                    try {
                        var instruction = pseudo.disassemble(cursor);
                        if (instruction == null) {
                            break;
                        }
                        if (step == 0) {
                            prologue = instruction.toString().replace(' ', '_');
                        }
                        decoded++;
                        cursor = cursor.add(instruction.getLength());
                    } catch (Exception exception) {
                        break;
                    }
                }
            }
            println("TARGET addr=0x" + Long.toHexString(target)
                + " thumb=" + thumb
                + " mapped=" + isMapped
                + " valid_subroutine=" + valid
                + " decoded=" + decoded
                + " prologue=" + prologue
                + " defined=" + (existing != null)
                + " at=" + (existing == null ? "none" : existing.getName()));
            if (decoded >= 8) {
                validated++;
            }
        }

        // 5A's exit gate asks for the remaining unresolved indirect calls to
        // be ENUMERATED, not eliminated. Every register-target branch is
        // listed with whether constant propagation resolves its register, so
        // the gap has a number and an address list rather than a shrug.
        if (indirect) {
            int total = 0;
            int known = 0;
            FunctionIterator functions = currentProgram.getFunctionManager()
                .getFunctions(true);
            while (functions.hasNext()) {
                Function function = functions.next();
                if (function.isExternal() || function.isThunk()) {
                    continue;
                }
                SymbolicPropogator propagator =
                    new SymbolicPropogator(currentProgram);
                propagator.flowConstants(function.getEntryPoint(),
                    function.getBody(),
                    new ConstantPropagationContextEvaluator(monitor, true),
                    false, monitor);
                InstructionIterator instructions = currentProgram.getListing()
                    .getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    String mnemonic =
                        instruction.getMnemonicString().toLowerCase();
                    if (!mnemonic.equals("blx") && !mnemonic.equals("bx")) {
                        continue;
                    }
                    Object[] parts = instruction.getOpObjects(0);
                    if (parts.length != 1 || !(parts[0] instanceof Register)) {
                        continue;
                    }
                    Register register = (Register) parts[0];
                    if (mnemonic.equals("bx")
                        && register.getName().equalsIgnoreCase("lr")) {
                        // A plain function return, not an indirect call.
                        continue;
                    }
                    Value value = propagator.getRegisterValue(
                        instruction.getAddress(), register);
                    total++;
                    if (value != null) {
                        known++;
                    }
                    println("INDIRECT instr=" + instruction.getAddress()
                        + " func=" + function.getEntryPoint()
                        + " mnemonic=" + mnemonic
                        + " register=" + register.getName()
                        + " target=" + show(value));
                }
            }
            println("INDIRECT_RESULT sites=" + total + " resolved=" + known
                + " unresolved=" + (total - known));
        }

        int callsites = 0;
        int resolved = 0;
        int partial = 0;
        for (long value : primitives) {
            Address entry = addr(value & ~1L);
            Function primitive = getFunctionAt(entry);
            if (primitive == null) {
                println("PRIMITIVE entry=" + entry + " name=none params=0 "
                    + "body=none callers=0 reason=no_function_at_address");
                continue;
            }
            List<Reference> calls = new ArrayList<>();
            ReferenceIterator references = currentProgram.getReferenceManager()
                .getReferencesTo(entry);
            while (references.hasNext()) {
                Reference reference = references.next();
                if (reference.getReferenceType().isCall()) {
                    calls.add(reference);
                }
            }
            println("PRIMITIVE entry=" + entry
                + " name=" + primitive.getName()
                + " params=" + primitive.getParameterCount()
                + " body=" + primitive.getBody().getMinAddress() + ".."
                + primitive.getBody().getMaxAddress()
                + " callers=" + calls.size());

            calls.sort((left, right) ->
                left.getFromAddress().compareTo(right.getFromAddress()));
            int order = 0;
            for (Reference reference : calls) {
                Address site = reference.getFromAddress();
                Function caller = getFunctionContaining(site);
                if (caller == null) {
                    println("CALLSITE primitive=" + entry + " instr=" + site
                        + " func=none order=" + order
                        + " a0=unknown a1=unknown a2=unknown a3=unknown"
                        + " a4=unknown a5=unknown str=none"
                        + " reason=call_site_in_no_function");
                    callsites++;
                    partial++;
                    order++;
                    continue;
                }
                Instruction call = getInstructionAt(site);
                SymbolicPropogator propagator =
                    new SymbolicPropogator(currentProgram);
                propagator.flowConstants(caller.getEntryPoint(),
                    caller.getBody(),
                    new ConstantPropagationContextEvaluator(monitor, true),
                    false, monitor);

                StringBuilder line = new StringBuilder();
                boolean complete = true;
                String text = null;
                for (int index = 0; index < ARG_REGISTERS.length; index++) {
                    Register register =
                        currentProgram.getRegister(ARG_REGISTERS[index]);
                    Value found = register == null ? null
                        : propagator.getRegisterValue(site, register);
                    line.append(" a").append(index).append("=")
                        .append(show(found));
                    if (found == null) {
                        complete = false;
                    } else if (index == 1) {
                        text = stringAt(found.getValue());
                    }
                }
                for (int index = 0; index < STACK_SLOTS.length; index++) {
                    Value found = stackArgument(propagator, caller, call,
                        STACK_SLOTS[index]);
                    line.append(" a").append(ARG_REGISTERS.length + index)
                        .append("=").append(show(found));
                    if (found == null) {
                        complete = false;
                    }
                }
                println("CALLSITE primitive=" + entry + " instr=" + site
                    + " func=" + caller.getEntryPoint()
                    + " order=" + order
                    + line
                    + " str=" + (text == null ? "none" : text));
                callsites++;
                order++;
                if (complete) {
                    resolved++;
                } else {
                    partial++;
                }
            }
        }
        println("RESULT callsites=" + callsites + " resolved=" + resolved
            + " partial=" + partial + " validated=" + validated);
    }
}
