// Read-only focused report for Candidate B key-remap commands 0x51/0x21-0x22.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

public class FalchionKeyRemapReport extends GhidraScript {
    private void printInstructionRange(long startValue, long endValue) {
        Address start = toAddr(startValue);
        Address end = toAddr(endValue);
        println("INSTRUCTIONS " + start + ".." + end);
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
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            println("  " + instruction.getAddress() + "  " + instruction +
                "  owner=" + (owner == null ? "none" : owner.getName() + "@" +
                    owner.getEntryPoint()) +
                (refs.length() == 0 ? "" : "  refs=[" + refs + "]"));
            instruction = instruction.getNext();
        }
    }

    private void printLiteral(long addressValue) throws Exception {
        Address address = toAddr(addressValue);
        Memory memory = currentProgram.getMemory();
        long value = Integer.toUnsignedLong(memory.getInt(address));
        StringBuilder refs = new StringBuilder();
        for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(address)) {
            if (refs.length() > 0) {
                refs.append(",");
            }
            refs.append(ref.getReferenceType()).append("<-").append(ref.getFromAddress());
        }
        println(String.format("LITERAL %s value=0x%08x%s", address, value,
            refs.length() == 0 ? "" : " refs=[" + refs + "]"));
    }

    private void printFunctionReferences(long addressValue) {
        Address address = toAddr(addressValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(address);
        if (function == null) {
            println("FUNCTION address=" + address + " none");
            return;
        }
        println("FUNCTION " + function.getName() + " entry=" + function.getEntryPoint() +
            " body=" + function.getBody());
        for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(address)) {
            println("  reference from=" + ref.getFromAddress() + " type=" +
                ref.getReferenceType());
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
        String programName = currentProgram.getName();
        long base;
        if (programName.equals("app_candidate_b.bin")) {
            base = 0L;
        }
        else if (programName.equals("app_candidate_b_18000000.bin")) {
            base = 0x18000000L;
        }
        else {
            println("This report is scoped to app_candidate_b.bin; current=" +
                programName);
            return;
        }

        println("PROGRAM " + programName + " base=" + toAddr(base));
        println("PURPOSE offline read-only report; no device access and no project mutation");
        printInstructionRange(base + 0x2662L, base + 0x27d5L);
        for (long address : new long[] {
            0x29b4L, 0x29b8L, 0x29bcL, 0x29c0L, 0x29c4L, 0x29c8L
        }) {
            printLiteral(base + address);
        }

        for (long address : new long[] {
            0x1fbeL, 0x2718L, 0x0a70L, 0x1bdbaL, 0x06daL
        }) {
            printFunctionReferences(base + address);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            decompile(base + 0x2718L, decompiler);
            decompile(base + 0x0a70L, decompiler);
            decompile(base + 0x1bdbaL, decompiler);
            decompile(base + 0x06daL, decompiler);
        }
        finally {
            decompiler.dispose();
        }
    }
}
