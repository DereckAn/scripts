// Read-only report for Candidate B's KBID selector and overlapping key maps.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

public class FalchionKbidMapReport extends GhidraScript {
    private static final long BASE = 0x18000000L;
    private static final long SELECTOR_STATE = 0x1801ee64L;
    private static final long SELECTOR_ADDRESS = SELECTOR_STATE + 8L;
    private static final long MAP_ADDRESS = 0x1801c37cL;
    private static final int MAP_STRIDE = 0x86;
    private static final int MAP_LOGICAL_LENGTH = 0xbd;
    private static final int SELECTOR_COUNT = 3;
    private static final long SCAN_MAP_ADDRESS = 0x1801c50eL;
    private static final int SCAN_MAP_STRIDE = 0x100;
    private static final long POLICY_ADDRESS = 0x1801c810L;

    private void printFunction(long addressValue, DecompInterface decompiler) {
        Address address = toAddr(addressValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(address);
        if (function == null) {
            function = currentProgram.getFunctionManager().getFunctionContaining(address);
        }
        if (function == null) {
            println("FUNCTION requested=" + address + " none");
            return;
        }

        println("FUNCTION requested=" + address + " name=" + function.getName() +
            " entry=" + function.getEntryPoint() + " body=" + function.getBody());
        for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(
                function.getEntryPoint())) {
            println("  CALLER from=" + reference.getFromAddress() + " type=" +
                reference.getReferenceType());
        }

        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        println("DECOMPILE completed=" + result.decompileCompleted() + " error=" +
            result.getErrorMessage());
        if (result.getDecompiledFunction() != null) {
            println(result.getDecompiledFunction().getC());
        }
    }

    private void printReferences(String name, long startValue, long endValue) {
        println(String.format("REFERENCES %s 0x%08x..0x%08x", name, startValue,
            endValue));
        int count = 0;
        for (long value = startValue; value <= endValue; value++) {
            Address target = toAddr(value);
            for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(
                    target)) {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    reference.getFromAddress());
                println("  target=" + target + " from=" + reference.getFromAddress() +
                    " type=" + reference.getReferenceType() + " function=" +
                    (owner == null ? "none" : owner.getName() + "@" +
                        owner.getEntryPoint()));
                count++;
            }
        }
        println("REFERENCE_COUNT " + name + " " + count);
    }

    private void printLiteralWords(long startValue, long endValue) throws Exception {
        Memory memory = currentProgram.getMemory();
        println(String.format("LITERAL_WORDS 0x%08x..0x%08x", startValue, endValue));
        for (long value = startValue; value <= endValue; value += 4) {
            Address address = toAddr(value);
            long word = Integer.toUnsignedLong(memory.getInt(address));
            println(String.format("  %s 0x%08x", address, word));
        }
    }

    private void printBytes(String name, long startValue, int length) throws Exception {
        Memory memory = currentProgram.getMemory();
        byte[] bytes = new byte[length];
        memory.getBytes(toAddr(startValue), bytes);
        println(String.format("BYTES %s address=0x%08x length=0x%x", name, startValue,
            length));
        for (int offset = 0; offset < bytes.length; offset += 16) {
            StringBuilder line = new StringBuilder();
            line.append(String.format("  +0x%04x", offset));
            for (int index = offset; index < Math.min(offset + 16, bytes.length); index++) {
                line.append(String.format(" %02x", Byte.toUnsignedInt(bytes[index])));
            }
            println(line.toString());
        }
    }

    private void printInstructionRange(long startValue, long endValue) {
        println(String.format("INSTRUCTIONS 0x%08x..0x%08x", startValue, endValue));
        Instruction instruction = currentProgram.getListing().getInstructionAt(
            toAddr(startValue));
        if (instruction == null) {
            instruction = currentProgram.getListing().getInstructionAfter(toAddr(startValue));
        }
        while (instruction != null &&
                instruction.getAddress().compareTo(toAddr(endValue)) <= 0) {
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            println("  " + instruction.getAddress() + " " + instruction + " owner=" +
                (owner == null ? "none" : owner.getName() + "@" +
                    owner.getEntryPoint()));
            instruction = instruction.getNext();
        }
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only KBID selector and key-index-map report");
        if (!currentProgram.getName().equals("app_candidate_b_18000000.bin")) {
            println("This report requires the corrected-base Candidate B program");
            return;
        }

        println(String.format(
            "CONSTANTS base=0x%08x state=0x%08x selector=0x%08x map=0x%08x " +
            "map_stride=0x%x map_logical_length=0x%x selectors=%d " +
            "scan_map=0x%08x scan_stride=0x%x policy=0x%08x",
            BASE, SELECTOR_STATE, SELECTOR_ADDRESS, MAP_ADDRESS, MAP_STRIDE,
            MAP_LOGICAL_LENGTH, SELECTOR_COUNT, SCAN_MAP_ADDRESS, SCAN_MAP_STRIDE,
            POLICY_ADDRESS));

        printReferences("selector_state", SELECTOR_STATE, SELECTOR_ADDRESS + 3);
        printReferences("wire_map_before_shared_overlap", MAP_ADDRESS,
            SCAN_MAP_ADDRESS - 1);
        printReferences("shared_wire_scan_overlap", SCAN_MAP_ADDRESS,
            MAP_ADDRESS + (long) (SELECTOR_COUNT - 1) * MAP_STRIDE +
                MAP_LOGICAL_LENGTH - 1);
        printReferences("scan_map_after_shared_overlap",
            MAP_ADDRESS + (long) (SELECTOR_COUNT - 1) * MAP_STRIDE +
                MAP_LOGICAL_LENGTH, POLICY_ADDRESS - 3);

        for (int selector = 0; selector < SELECTOR_COUNT; selector++) {
            long windowAddress = MAP_ADDRESS + (long) selector * MAP_STRIDE;
            printBytes("wire_window_selector_" + selector, windowAddress,
                MAP_LOGICAL_LENGTH);
        }
        for (int selector = 0; selector < SELECTOR_COUNT; selector++) {
            long scanAddress = SCAN_MAP_ADDRESS + (long) selector * SCAN_MAP_STRIDE;
            printBytes("scan_map_selector_" + selector, scanAddress,
                SCAN_MAP_STRIDE);
        }
        printBytes("padding_before_policy", POLICY_ADDRESS - 2, 2);

        printLiteralWords(BASE + 0x8cc0L, BASE + 0x8d20L);
        printInstructionRange(BASE + 0x88eaL, BASE + 0x8990L);

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for (long functionAddress : new long[] {
                BASE + 0x88eaL,
                BASE + 0x4160L,
                BASE + 0x0466L,
                BASE + 0x57d2L,
                BASE + 0x1fbeL
            }) {
                printFunction(functionAddress, decompiler);
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
