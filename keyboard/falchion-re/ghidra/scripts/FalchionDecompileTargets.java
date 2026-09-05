// Decompile named addresses and print the decompiler output together with the
// instruction listing, callers, callees and the data the body references.
//
// The plan for this phase requires both views: a decompiler result alone can
// silently normalise a comparison's width or signedness, and a listing alone is
// hard to reason about. Printing them side by side lets every claim cite a real
// instruction span.
//
// Read-only: makes no change to the program database.
//
// Arguments: one or more addresses in hex, with or without a leading 0x. An
// address with no function is disassembled and reported as a raw listing so it
// is still visible rather than silently skipped.
//
// @category Falchion
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.symbol.Reference;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class FalchionDecompileTargets extends GhidraScript {

    private DecompInterface decompiler;

    private void report(Address address) throws Exception {
        Function function = getFunctionContaining(address);
        println("");
        println("=== TARGET " + address);
        if (function == null) {
            println("  NO_FUNCTION at this address; raw listing follows");
            Listing listing = currentProgram.getListing();
            Address cursor = address;
            for (int index = 0; index < 24; index++) {
                Instruction instruction = listing.getInstructionAt(cursor);
                if (instruction == null) {
                    println("  " + cursor + "  (no instruction)");
                    break;
                }
                println("  " + cursor + "  " + instruction);
                cursor = instruction.getAddress().add(instruction.getLength());
            }
            return;
        }

        println("  FUNCTION " + function.getName() + " @ "
            + function.getEntryPoint()
            + " size=0x" + Long.toHexString(function.getBody().getNumAddresses()));
        List<String> ranges = new ArrayList<>();
        for (AddressRange range : function.getBody().getAddressRanges(true)) {
            ranges.add(range.getMinAddress() + "-" + range.getMaxAddress());
        }
        println("  BODY_RANGES " + String.join(";", ranges));

        List<String> callers = new ArrayList<>();
        for (Function caller : function.getCallingFunctions(monitor)) {
            callers.add(caller.getName() + "@" + caller.getEntryPoint());
        }
        Collections.sort(callers);
        println("  CALLERS " + (callers.isEmpty() ? "none"
            : String.join(", ", callers)));

        List<String> callees = new ArrayList<>();
        for (Function callee : function.getCalledFunctions(monitor)) {
            callees.add(callee.getName() + "@" + callee.getEntryPoint());
        }
        Collections.sort(callees);
        println("  CALLEES " + (callees.isEmpty() ? "none"
            : String.join(", ", callees)));

        // Every datum the body reads or writes, with the word stored there.
        List<String> data = new ArrayList<>();
        Listing listing = currentProgram.getListing();
        InstructionIterator instructions =
            listing.getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                Address to = reference.getToAddress();
                if (!currentProgram.getMemory().contains(to)) {
                    data.add(instruction.getAddress() + " -> " + to
                        + " (outside this program)");
                    continue;
                }
                try {
                    int value = currentProgram.getMemory().getInt(to);
                    data.add(instruction.getAddress() + " -> " + to + " = 0x"
                        + Integer.toHexString(value));
                } catch (Exception exception) {
                    data.add(instruction.getAddress() + " -> " + to
                        + " (unreadable)");
                }
            }
        }
        Collections.sort(data);
        println("  REFERENCED_DATA " + data.size());
        for (String line : data) {
            println("    " + line);
        }

        println("  LISTING");
        instructions = listing.getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            println("    " + instruction.getAddress() + "  "
                + instruction.getBytes().length + "b  " + instruction);
        }

        println("  DECOMPILE");
        DecompileResults results =
            decompiler.decompileFunction(function, 60, monitor);
        if (results == null || !results.decompileCompleted()) {
            println("    FAILED "
                + (results == null ? "no result" : results.getErrorMessage()));
            return;
        }
        for (String line : results.getDecompiledFunction().getC().split("\n")) {
            println("    " + line);
        }
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("IMAGE_BASE " + currentProgram.getImageBase());
        String[] args = getScriptArgs();
        if (args.length == 0) {
            println("RESULT targets=0 error=no addresses supplied");
            return;
        }

        decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            int done = 0;
            for (String text : args) {
                String cleaned = text.replaceFirst("^0[xX]", "");
                Address address;
                try {
                    address = currentProgram.getAddressFactory()
                        .getDefaultAddressSpace()
                        .getAddress(Long.parseLong(cleaned, 16));
                } catch (NumberFormatException exception) {
                    println("SKIP " + text + " reason=unparseable_address");
                    continue;
                }
                if (!currentProgram.getMemory().contains(address)) {
                    println("SKIP " + address + " reason=outside_this_program");
                    continue;
                }
                report(address);
                done++;
            }
            println("");
            println("RESULT targets=" + done);
        } finally {
            decompiler.dispose();
        }
    }
}
