// Measure how much of a block decodes as Thumb-2, as a rate rather than a
// verdict. Thumb-2 is a dense encoding, so a block of real code decodes at
// nearly every 2-byte boundary and a block of data does not. The rate only
// means something against a control, so this is run on slices of known code as
// well as on the block in question.
//
// Read-only: it forces the TMode context register over the block so the
// decoder is asked the Thumb question rather than the ARM one, then reports
// counts. Run with -readOnly so nothing is saved; it creates no functions.
//
//@category Falchion
import java.math.BigInteger;

import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.mem.MemoryBlock;

public class FalchionRegionDisassembly extends GhidraScript {

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("MEASURE fraction of 2-byte boundaries at which the Thumb-2 "
            + "decoder yields an instruction");
        Register tmode = currentProgram.getProgramContext().getRegister("TMode");
        PseudoDisassembler pseudo = new PseudoDisassembler(currentProgram);
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            if (!block.isInitialized()) {
                continue;
            }
            if (tmode != null) {
                try {
                    currentProgram.getProgramContext().setValue(
                        tmode, block.getStart(), block.getEnd(), BigInteger.ONE);
                } catch (Exception exception) {
                    // A slice that already carries instructions rejects the
                    // change, and does not need it: its Thumb context is
                    // already established by those instructions.
                    println("NOTE TMode already fixed by existing instructions");
                }
            }
            long total = 0;
            long decoded = 0;
            long undefined = 0;
            Address address = block.getStart();
            while (address.compareTo(block.getEnd()) < 0) {
                total++;
                try {
                    PseudoInstruction instruction = pseudo.disassemble(address);
                    if (instruction == null) {
                        undefined++;
                    } else {
                        decoded++;
                    }
                } catch (Exception exception) {
                    undefined++;
                }
                try {
                    address = address.add(2);
                } catch (Exception exception) {
                    break;
                }
            }
            double rate = total == 0 ? 0.0 : (100.0 * decoded) / total;
            println(String.format(
                "BLOCK %s %s..%s boundaries=%d decoded=%d undefined=%d "
                + "rate=%.2f%%",
                block.getName(), block.getStart().toString(),
                block.getEnd().toString(), total, decoded, undefined, rate));
        }
        println("RESULT measurement complete");
    }
}
