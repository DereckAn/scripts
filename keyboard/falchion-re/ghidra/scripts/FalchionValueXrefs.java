// Find every place a 32-bit value is used, whether or not Ghidra made it a
// reference. Two independent passes, both reported:
//
//   LITERAL  the value appears as an aligned word in the image. On Cortex-M a
//            constant address almost always reaches a register through a
//            PC-relative load from a literal pool, so this is how most uses of
//            a RAM or MMIO address are actually spelled.
//   REF      Ghidra's reference manager has a reference to the address.
//   REG      constant propagation gives a register that exact value at an
//            instruction, which catches values built with movw/movt.
//
// A literal-pool word is reported with the function whose body contains it and
// with every instruction that loads from it, so a use is attributed to code
// rather than left as a bare offset.
//
// Read-only: makes no change to the program database.
// Arguments: one or more 32-bit values in hex.
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
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.util.SymbolicPropogator;
import ghidra.program.util.SymbolicPropogator.Value;

import java.util.ArrayList;
import java.util.List;

public class FalchionValueXrefs extends GhidraScript {

    private String where(Address address) {
        Function function = getFunctionContaining(address);
        return function == null ? "none"
            : function.getName() + "@" + function.getEntryPoint();
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        println("PROGRAM " + currentProgram.getName());
        List<Long> targets = new ArrayList<>();
        for (String argument : args) {
            targets.add(Long.parseLong(
                argument.trim().replaceFirst("^0[xX]", ""), 16));
        }

        int found = 0;
        for (long target : targets) {
            // Pass 1: aligned literal words holding the value.
            for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
                if (!block.isInitialized()) {
                    continue;
                }
                Address cursor = block.getStart();
                while (cursor.compareTo(block.getEnd()) < 0) {
                    long value;
                    try {
                        value = currentProgram.getMemory().getInt(cursor)
                            & 0xffffffffL;
                    } catch (Exception exception) {
                        break;
                    }
                    if (value == (target & 0xffffffffL)) {
                        StringBuilder loaders = new StringBuilder();
                        ReferenceIterator refs = currentProgram
                            .getReferenceManager().getReferencesTo(cursor);
                        while (refs.hasNext()) {
                            Reference reference = refs.next();
                            loaders.append(" loader=")
                                .append(reference.getFromAddress())
                                .append("(").append(
                                    where(reference.getFromAddress()))
                                .append(")");
                        }
                        println("LITERAL value=0x" + Long.toHexString(target)
                            + " at=" + cursor + " in=" + where(cursor)
                            + (loaders.length() == 0 ? " loader=none"
                                                     : loaders.toString()));
                        found++;
                    }
                    try {
                        cursor = cursor.add(4);
                    } catch (Exception exception) {
                        break;
                    }
                }
            }

            // Pass 2: Ghidra references to the address itself.
            try {
                Address address = currentProgram.getAddressFactory()
                    .getDefaultAddressSpace().getAddress(target);
                ReferenceIterator refs = currentProgram.getReferenceManager()
                    .getReferencesTo(address);
                while (refs.hasNext()) {
                    Reference reference = refs.next();
                    println("REF value=0x" + Long.toHexString(target)
                        + " from=" + reference.getFromAddress()
                        + " in=" + where(reference.getFromAddress())
                        + " type=" + reference.getReferenceType());
                    found++;
                }
            } catch (Exception exception) {
                // Not an address in this program's space; literals still count.
            }
        }

        // Pass 3: a register holding the value at some instruction.
        FunctionIterator functions =
            currentProgram.getFunctionManager().getFunctions(true);
        while (functions.hasNext()) {
            Function function = functions.next();
            if (function.isExternal() || function.isThunk()) {
                continue;
            }
            SymbolicPropogator propagator = new SymbolicPropogator(currentProgram);
            propagator.flowConstants(function.getEntryPoint(), function.getBody(),
                new ConstantPropagationContextEvaluator(monitor, true), false,
                monitor);
            InstructionIterator instructions =
                currentProgram.getListing().getInstructions(function.getBody(), true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (Object part : instruction.getResultObjects()) {
                    if (!(part instanceof Register)) {
                        continue;
                    }
                    Value value = propagator.getRegisterValue(
                        instruction.getAddress(), (Register) part);
                    if (value == null) {
                        continue;
                    }
                    for (long target : targets) {
                        if ((value.getValue() & 0xffffffffL)
                                == (target & 0xffffffffL)) {
                            println("REG value=0x" + Long.toHexString(target)
                                + " instr=" + instruction.getAddress()
                                + " in=" + function.getName() + "@"
                                + function.getEntryPoint()
                                + " reg=" + ((Register) part).getName());
                            found++;
                        }
                    }
                }
            }
        }
        println("RESULT uses=" + found + " targets=" + targets.size());
    }
}
