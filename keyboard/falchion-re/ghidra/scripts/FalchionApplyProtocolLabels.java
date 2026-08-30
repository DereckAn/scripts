// Apply only evidence-supported protocol labels to the local Ghidra project.
// @category Falchion

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class FalchionApplyProtocolLabels extends GhidraScript {
    private void label(long addressValue, String newName) throws Exception {
        Address address = toAddr(addressValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(address);
        if (function == null) {
            println("missing function at " + address + "; not labeled");
            return;
        }
        String oldName = function.getName();
        if (oldName.equals(newName)) {
            println("already labeled " + address + " " + newName);
            return;
        }
        if (!oldName.startsWith("FUN_")) {
            println("preserved non-default label at " + address + " name=" + oldName);
            return;
        }
        function.setName(newName, SourceType.USER_DEFINED);
        println("renamed " + address + " " + oldName + " -> " + newName);
    }

    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("app_candidate_b.bin")) {
            println("This script is scoped to app_candidate_b.bin; current=" +
                currentProgram.getName());
            return;
        }
        println("PROGRAM " + currentProgram.getName());
        println("SCOPE local Ghidra analysis database only; source BIN and device untouched");
        label(0x1f6eL, "IsKeyUnsupportedForLayer");
        label(0x1fbeL, "VendorHID_CommandDispatcher");
        label(0x0a70L, "VendorHID_SendResponse64");
    }
}
