// Read-only disassembly and decompiler report for Candidate B opcode-dispatch regions.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class FalchionDispatcherReport extends GhidraScript {
    private static final long[][] REGIONS = {
        {0x1fbeL, 0x2040L},
        {0x23c0L, 0x2510L},
        {0x2640L, 0x2690L},
        {0x2760L, 0x27c0L},
        {0x2be0L, 0x2c40L},
        {0x3170L, 0x31c0L},
        {0x3fa0L, 0x4002L}
    };

    private void printRegion(long startValue, long endValue) {
        Address start = toAddr(startValue);
        Address end = toAddr(endValue);
        println("REGION " + start + ".." + end);
        Instruction instruction = currentProgram.getListing().getInstructionAt(start);
        if (instruction == null) {
            instruction = currentProgram.getListing().getInstructionAfter(start);
        }
        while (instruction != null && instruction.getAddress().compareTo(end) <= 0) {
            StringBuilder refs = new StringBuilder();
            for (Reference ref : instruction.getReferencesFrom()) {
                if (refs.length() > 0) {
                    refs.append(",");
                }
                refs.append(ref.getReferenceType()).append("->").append(ref.getToAddress());
            }
            println("  " + instruction.getAddress() + "  " + instruction +
                (refs.length() == 0 ? "" : "  refs=[" + refs + "]"));
            instruction = instruction.getNext();
        }
    }

    private void decompile(long addressValue, DecompInterface decompiler) {
        Address address = toAddr(addressValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(address);
        if (function == null) {
            function = currentProgram.getFunctionManager().getFunctionContaining(address);
        }
        if (function == null) {
            println("DECOMPILE address=" + address + " function=none");
            return;
        }
        println("DECOMPILE function=" + function.getName() + " entry=" +
            function.getEntryPoint());
        DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
        println("  completed=" + result.decompileCompleted() + " error=" +
            result.getErrorMessage());
        if (result.getDecompiledFunction() != null) {
            println(result.getDecompiledFunction().getC());
        }
    }

    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("app_candidate_b.bin")) {
            println("This report is scoped to app_candidate_b.bin; current=" +
                currentProgram.getName());
            return;
        }
        println("PROGRAM " + currentProgram.getName());
        for (long[] region : REGIONS) {
            printRegion(region[0], region[1]);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            decompile(0x1fbeL, decompiler);
            decompile(0x2718L, decompiler);
            decompile(0x1bd60L, decompiler);
        }
        finally {
            decompiler.dispose();
        }
    }
}
