// Read-only report for Candidate A reset, scatter loading, and Candidate B load records.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

public class FalchionCandidateALoaderReport extends GhidraScript {
    private void printWords(long startValue, long endValue) throws Exception {
        Memory memory = currentProgram.getMemory();
        println(String.format("WORDS 0x%08x..0x%08x", startValue, endValue));
        for (long value = startValue; value <= endValue; value += 4) {
            println(String.format("  %s 0x%08x", toAddr(value),
                Integer.toUnsignedLong(memory.getInt(toAddr(value)))));
        }
    }

    private void printInstructions(long startValue, long endValue) {
        println(String.format("INSTRUCTIONS 0x%08x..0x%08x", startValue, endValue));
        Instruction instruction = currentProgram.getListing().getInstructionAt(
            toAddr(startValue));
        if (instruction == null) {
            instruction = currentProgram.getListing().getInstructionAfter(toAddr(startValue));
        }
        while (instruction != null &&
                instruction.getAddress().compareTo(toAddr(endValue)) <= 0) {
            StringBuilder refs = new StringBuilder();
            for (Reference reference : instruction.getReferencesFrom()) {
                if (refs.length() > 0) refs.append(",");
                refs.append(reference.getReferenceType()).append("->")
                    .append(reference.getToAddress());
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            println("  " + instruction.getAddress() + " " + instruction + " owner=" +
                (owner == null ? "none" : owner.getName() + "@" +
                    owner.getEntryPoint()) +
                (refs.length() == 0 ? "" : " refs=[" + refs + "]"));
            instruction = instruction.getNext();
        }
    }

    private void printReferences(String name, long addressValue) {
        Address address = toAddr(addressValue);
        println("REFERENCES " + name + " target=" + address);
        int count = 0;
        for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(
                address)) {
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            println("  from=" + reference.getFromAddress() + " type=" +
                reference.getReferenceType() + " function=" +
                (owner == null ? "none" : owner.getName() + "@" +
                    owner.getEntryPoint()));
            count++;
        }
        println("REFERENCE_COUNT " + name + " " + count);
    }

    private void decompile(long addressValue, DecompInterface decompiler) {
        Address address = toAddr(addressValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(address);
        if (function == null) {
            function = currentProgram.getFunctionManager().getFunctionContaining(address);
        }
        if (function == null) {
            println("DECOMPILE requested=" + address + " function=none");
            return;
        }
        println("DECOMPILE requested=" + address + " function=" + function.getName() +
            " entry=" + function.getEntryPoint() + " body=" + function.getBody());
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        println("  completed=" + result.decompileCompleted() + " error=" +
            result.getErrorMessage());
        if (result.getDecompiledFunction() != null) {
            println(result.getDecompiledFunction().getC());
        }
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only Candidate A loader/scatter report");
        if (!currentProgram.getName().equals("app_candidate_a.bin")) {
            println("This report requires app_candidate_a.bin");
            return;
        }

        println("EPHEMERAL_DISASSEMBLY indirect scatter handlers; read-only project is not saved");
        println("  decompress_0x017c=" + disassemble(toAddr(0x017cL)));
        println("  zeroinit_0x01f4=" + disassemble(toAddr(0x01f4L)));

        printWords(0x14e0L, 0x14f4L);
        printWords(0x5750L, 0x579cL);
        printWords(0x0f70L, 0x0fb0L);

        for (long address : new long[] {
            0x0140L, 0x0148L, 0x017cL, 0x01d8L, 0x01f4L,
            0x0fa0L, 0x1216L, 0x14a8L, 0x5750L
        }) {
            printReferences(String.format("address_0x%04x", address), address);
        }

        printInstructions(0x0140L, 0x0210L);
        printInstructions(0x0e80L, 0x1020L);
        printInstructions(0x14a8L, 0x14f4L);

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for (long address : new long[] {
                0x0140L, 0x0148L, 0x017cL, 0x01d8L, 0x01f4L,
                0x0e80L, 0x0fa0L, 0x1216L, 0x14a8L
            }) {
                decompile(address, decompiler);
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
