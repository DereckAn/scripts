// Seed only entry points supported by offline vector/code analysis.
// This changes the local Ghidra project database, never the source BIN or device.
// @category Falchion

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

public class FalchionSeedEntries extends GhidraScript {
    private void label(long value, String name) throws Exception {
        Address address = toAddr(value);
        createLabel(address, name, true);
        println("  label " + address + " " + name);
    }

    private void seedFunction(long value, String name) throws Exception {
        Address address = toAddr(value);
        FunctionManager functions = currentProgram.getFunctionManager();
        Function at = functions.getFunctionAt(address);
        Function containing = functions.getFunctionContaining(address);

        if (at != null) {
            at.setName(name, ghidra.program.model.symbol.SourceType.USER_DEFINED);
            println("  renamed existing function at " + address + " to " + name);
            return;
        }
        if (containing != null) {
            createLabel(address, name, true);
            println("  preserved containing function " + containing.getName() +
                "; added entry label " + name + " at " + address);
            return;
        }

        disassemble(address);
        Function created = createFunction(address, name);
        if (created == null) {
            println("  WARNING could not create function " + name + " at " + address);
        }
        else {
            println("  created function " + created.getName() + " at " + address);
        }
    }

    @Override
    public void run() throws Exception {
        String name = currentProgram.getName();
        println("PROGRAM " + name);

        if (name.equals("bootloader_primary.bin")) {
            label(0x00000000L, "Bootloader_Vector_Table");
            seedFunction(0x000002f4L, "Bootloader_Reset_Entry");
        }
        else if (name.equals("app_candidate_a.bin")) {
            label(0x00000000L, "CandidateA_Vector_Table");
            seedFunction(0x000014a8L, "CandidateA_Reset_Handler");
        }
        else if (name.equals("app_candidate_b.bin")) {
            seedFunction(0x00000000L, "CandidateB_Start_Function");
        }
        else if (name.equals("app_candidate_b_18000000.bin")) {
            seedFunction(0x18000000L, "CandidateB_Start_Function");
            seedFunction(0x18001fbeL, "VendorHID_CommandDispatcher");
        }
        else if (name.equals("ram_image_18038000.bin")) {
            label(0x18038000L, "RAM_Image_Vector_Table");
            seedFunction(0x180381c0L, "RAM_Image_Reset_Entry");
        }
        else {
            println("  no seed map for this program; unchanged");
        }
    }
}
