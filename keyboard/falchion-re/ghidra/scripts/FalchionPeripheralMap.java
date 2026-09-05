// Enumerate every load and store whose resolved target lies outside this
// program's own memory, i.e. every MMIO or external-RAM access. Read-only:
// makes no change to the program database.
//
// Base addresses are resolved with Ghidra's constant propagation rather than
// guessed from literal pools, so an access is reported only when the base
// register's value is actually known at that instruction. Accesses whose base
// cannot be resolved are counted and reported as unresolved rather than
// silently dropped, because an incomplete map that looks complete is worse than
// one that states its gaps.
//
// Output lines:
//   ACCESS target=<addr> width=<bytes> dir=read|write instr=<addr>
//          func=<entry> base=<reg>@<value> off=<signed> stored=<value|unknown>
//   UNRESOLVED instr=<addr> func=<entry> mnemonic=<m> reason=<why>
//   RESULT accesses=<n> unresolved=<n> functions=<n>
//
// @category Falchion
import ghidra.app.plugin.core.analysis.ConstantPropagationContextEvaluator;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.util.SymbolicPropogator;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class FalchionPeripheralMap extends GhidraScript {

    /** Access width in bytes, or 0 when the mnemonic is not a load/store. */
    private static int widthOf(String mnemonic) {
        String m = mnemonic.toLowerCase();
        if (!m.startsWith("ldr") && !m.startsWith("str")) {
            return 0;
        }
        // Strip the ldr/str prefix and any condition suffix.
        String rest = m.substring(3);
        if (rest.startsWith("b")) {
            return 1;
        }
        if (rest.startsWith("h")) {
            return 2;
        }
        if (rest.startsWith("d")) {
            return 8;
        }
        if (rest.isEmpty() || rest.startsWith("s") || rest.startsWith("e")
            || rest.startsWith("t") || rest.startsWith(".")) {
            // ldr, ldrsb/ldrsh (signed), ldrex/strex, ldrt/strt.
            if (rest.startsWith("sb")) {
                return 1;
            }
            if (rest.startsWith("sh")) {
                return 2;
            }
            return 4;
        }
        return 4;
    }

    private boolean insideThisProgram(long target) {
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            long start = block.getStart().getOffset();
            long end = block.getEnd().getOffset();
            if (target >= start && target <= end) {
                return true;
            }
        }
        return false;
    }

    @Override
    public void run() throws Exception {
        Listing listing = currentProgram.getListing();
        println("PROGRAM " + currentProgram.getName());
        println("IMAGE_BASE " + currentProgram.getImageBase());
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            println("BLOCK " + block.getName() + " " + block.getStart() + " "
                + block.getEnd());
        }

        List<String> lines = new ArrayList<>();
        int accesses = 0;
        int unresolved = 0;
        int functions = 0;

        FunctionIterator iterator = currentProgram.getFunctionManager()
            .getFunctions(true);
        while (iterator.hasNext()) {
            Function function = iterator.next();
            if (function.isExternal() || function.isThunk()) {
                continue;
            }
            functions++;

            SymbolicPropogator propagator = new SymbolicPropogator(currentProgram);
            propagator.flowConstants(function.getEntryPoint(), function.getBody(),
                new ConstantPropagationContextEvaluator(monitor, true), false,
                monitor);

            InstructionIterator instructions =
                listing.getInstructions(function.getBody(), true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                int width = widthOf(instruction.getMnemonicString());
                if (width == 0 || instruction.getNumOperands() < 2) {
                    continue;
                }
                boolean isWrite = instruction.getMnemonicString()
                    .toLowerCase().startsWith("str");

                // The memory operand is the last one for these forms.
                int memoryOperand = instruction.getNumOperands() - 1;
                Register base = null;
                long offset = 0;
                boolean sawSecondRegister = false;
                Address literal = null;
                for (Object part : instruction.getOpObjects(memoryOperand)) {
                    if (part instanceof Register) {
                        if (base == null) {
                            base = (Register) part;
                        } else {
                            sawSecondRegister = true;
                        }
                    } else if (part instanceof Scalar) {
                        offset = ((Scalar) part).getSignedValue();
                    } else if (part instanceof Address) {
                        literal = (Address) part;
                    }
                }
                if (base == null && literal != null) {
                    // PC-relative literal load: the target is known exactly and
                    // is the literal pool, which lives inside this image.
                    if (insideThisProgram(literal.getOffset())) {
                        continue;
                    }
                    lines.add("ACCESS target=0x"
                        + Long.toHexString(literal.getOffset() & 0xffffffffL)
                        + " width=" + width
                        + " dir=" + (isWrite ? "write" : "read")
                        + " instr=" + instruction.getAddress()
                        + " func=" + function.getEntryPoint()
                        + " base=pc@0x" + Long.toHexString(literal.getOffset())
                        + " off=0 stored=unknown");
                    accesses++;
                    continue;
                }
                if (base == null) {
                    lines.add("UNRESOLVED instr=" + instruction.getAddress()
                        + " func=" + function.getEntryPoint()
                        + " mnemonic=" + instruction.getMnemonicString()
                        + " reason=no_base_register");
                    unresolved++;
                    continue;
                }
                if (base.getName().equalsIgnoreCase("sp")) {
                    // Stack-relative: not a peripheral, and the stack pointer's
                    // value is a runtime property rather than a static fact.
                    lines.add("UNRESOLVED instr=" + instruction.getAddress()
                        + " func=" + function.getEntryPoint()
                        + " mnemonic=" + instruction.getMnemonicString()
                        + " reason=stack_relative");
                    unresolved++;
                    continue;
                }
                if (sawSecondRegister) {
                    lines.add("UNRESOLVED instr=" + instruction.getAddress()
                        + " func=" + function.getEntryPoint()
                        + " mnemonic=" + instruction.getMnemonicString()
                        + " reason=register_offset");
                    unresolved++;
                    continue;
                }

                SymbolicPropogator.Value value = propagator.getRegisterValue(
                    instruction.getAddress(), base);
                if (value == null || value.isRegisterRelativeValue()) {
                    lines.add("UNRESOLVED instr=" + instruction.getAddress()
                        + " func=" + function.getEntryPoint()
                        + " mnemonic=" + instruction.getMnemonicString()
                        + " reason=base_" + base.getName() + "_unknown");
                    unresolved++;
                    continue;
                }

                // Mask to 32 bits: getValue() sign-extends, which would
                // render 0xe000e010 as 0xffffffffe000e010.
                long target = (value.getValue() + offset) & 0xffffffffL;
                if (insideThisProgram(target)) {
                    continue;
                }

                String stored = "unknown";
                if (isWrite) {
                    Object[] source = instruction.getOpObjects(0);
                    if (source.length == 1 && source[0] instanceof Register) {
                        SymbolicPropogator.Value held =
                            propagator.getRegisterValue(instruction.getAddress(),
                                (Register) source[0]);
                        if (held != null && !held.isRegisterRelativeValue()) {
                            stored = "0x" + Long.toHexString(
                                held.getValue() & 0xffffffffL);
                        }
                    } else if (source.length == 1 && source[0] instanceof Scalar) {
                        stored = "0x" + Long.toHexString(
                            ((Scalar) source[0]).getUnsignedValue());
                    }
                }

                lines.add("ACCESS target=0x" + Long.toHexString(target)
                    + " width=" + width
                    + " dir=" + (isWrite ? "write" : "read")
                    + " instr=" + instruction.getAddress()
                    + " func=" + function.getEntryPoint()
                    + " base=" + base.getName() + "@0x"
                    + Long.toHexString(value.getValue())
                    + " off=" + offset
                    + " stored=" + stored);
                accesses++;
            }
        }
        Collections.sort(lines);
        for (String line : lines) {
            println(line);
        }
        println("RESULT accesses=" + accesses + " unresolved=" + unresolved
            + " functions=" + functions);
    }
}
