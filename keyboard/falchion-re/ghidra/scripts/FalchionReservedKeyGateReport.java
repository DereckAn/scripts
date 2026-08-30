// Read-only focused report for the possible unsupported/reserved-key gate.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class FalchionReservedKeyGateReport extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("app_candidate_b.bin")) {
            println("This report is scoped to app_candidate_b.bin; current=" +
                currentProgram.getName());
            return;
        }
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only possible reserved-key gate report; no device access and no project mutation");

        Address entry = toAddr(0x1f6eL);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        println("FUNCTION " + function.getName() + " entry=" + function.getEntryPoint() +
            " body=" + function.getBody());
        for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(entry)) {
            Function caller = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            println("  reference from=" + reference.getFromAddress() + " type=" +
                reference.getReferenceType() + " caller=" +
                (caller == null ? "none" : caller.getName() + "@" +
                    caller.getEntryPoint()));
        }

        for (Instruction instruction : currentProgram.getListing().getInstructions(
                function.getBody(), true)) {
            StringBuilder refs = new StringBuilder();
            for (Reference reference : instruction.getReferencesFrom()) {
                if (refs.length() > 0) {
                    refs.append(",");
                }
                refs.append(reference.getReferenceType()).append("->").append(
                    reference.getToAddress());
            }
            println("  " + instruction.getAddress() + "  " + instruction +
                (refs.length() == 0 ? "" : " refs=[" + refs + "]"));
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
            println("DECOMPILE completed=" + result.decompileCompleted() + " error=" +
                result.getErrorMessage());
            if (result.getDecompiledFunction() != null) {
                println(result.getDecompiledFunction().getC());
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
