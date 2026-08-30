// Read-only report for Candidate B key-configuration initialization/consumers.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class FalchionKeyConfigInitReport extends GhidraScript {
    private void report(long addressValue, DecompInterface decompiler) {
        Address address = toAddr(addressValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(address);
        if (function == null) {
            function = currentProgram.getFunctionManager().getFunctionContaining(address);
        }
        if (function == null) {
            println("FUNCTION address=" + address + " none");
            return;
        }

        println("FUNCTION " + function.getName() + " entry=" + function.getEntryPoint() +
            " body=" + function.getBody());
        for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(
                function.getEntryPoint())) {
            Function caller = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            println("  reference from=" + reference.getFromAddress() + " type=" +
                reference.getReferenceType() + " caller=" +
                (caller == null ? "none" : caller.getName() + "@" +
                    caller.getEntryPoint()));
        }

        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        println("DECOMPILE function=" + function.getName() + " completed=" +
            result.decompileCompleted() + " error=" + result.getErrorMessage());
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
        println("PURPOSE offline read-only initializer/consumer report; no device access and no project mutation");

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for (long address : new long[] {
                0x075aL, 0x254cL, 0x05faL, 0x7e0cL, 0x88eaL
            }) {
                report(address, decompiler);
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
