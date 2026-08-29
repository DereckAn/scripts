// Read-only project summary for the Falchion Ace HFX firmware slices.
// @category Falchion

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.MemoryBlock;

public class FalchionProjectReport extends GhidraScript {
    private long knownResetAddress(String name) {
        if (name.equals("bootloader_primary.bin")) {
            return 0x000002f4L;
        }
        if (name.equals("app_candidate_a.bin")) {
            return 0x000014a8L;
        }
        if (name.equals("app_candidate_b.bin")) {
            return 0x00000000L;
        }
        if (name.equals("ram_image_18038000.bin")) {
            return 0x180381c0L;
        }
        return -1;
    }

    @Override
    public void run() throws Exception {
        String name = currentProgram.getName();
        println("PROGRAM " + name);
        println("  language=" + currentProgram.getLanguageID());
        println("  compiler=" + currentProgram.getCompilerSpec().getCompilerSpecID());
        println("  image_base=" + currentProgram.getImageBase());

        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            println("  block=" + block.getName() + " start=" + block.getStart() +
                " end=" + block.getEnd() + " size=0x" + Long.toHexString(block.getSize()));
        }

        FunctionManager functions = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        int instructionCount = 0;
        InstructionIterator instructions = listing.getInstructions(true);
        while (instructions.hasNext()) {
            instructions.next();
            instructionCount++;
        }
        println("  functions=" + functions.getFunctionCount());
        println("  instructions=" + instructionCount);

        long resetValue = knownResetAddress(name);
        if (resetValue >= 0) {
            Address reset = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(resetValue);
            Function at = functions.getFunctionAt(reset);
            Function containing = functions.getFunctionContaining(reset);
            println("  known_entry=" + reset + " function_at=" +
                (at == null ? "none" : at.getName()) + " function_containing=" +
                (containing == null ? "none" : containing.getName()));
        }

        println("  relevant_strings:");
        int stringCount = 0;
        for (Data data : listing.getDefinedData(true)) {
            Object value = data.getValue();
            if (!(value instanceof String)) {
                continue;
            }
            String text = ((String) value).replace("\n", "\\n").replace("\r", "\\r");
            String lower = text.toLowerCase();
            if (lower.contains("usb") || lower.contains("hid") || lower.contains("keyboard") ||
                lower.contains("macro") || lower.contains("flash") || lower.contains("boot") ||
                lower.contains("fault") || lower.contains("feature") || lower.contains("asus") ||
                lower.contains("falchion") || lower.contains("sleep") || lower.contains("wake")) {
                println("    " + data.getAddress() + " " + text);
                stringCount++;
            }
        }
        println("  relevant_string_count=" + stringCount);
    }
}
