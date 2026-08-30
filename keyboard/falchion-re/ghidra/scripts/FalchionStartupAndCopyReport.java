// Read-only startup and memcpy-caller report for the four preserved programs.
// @category Falchion

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class FalchionStartupAndCopyReport extends GhidraScript {
    private long rootAddress() {
        String name = currentProgram.getName();
        if (name.equals("bootloader_primary.bin")) return 0x2f4L;
        if (name.equals("app_candidate_a.bin")) return 0x14a8L;
        if (name.equals("app_candidate_b.bin")) return 0x0L;
        if (name.equals("ram_image_18038000.bin")) return 0x180381c0L;
        return -1L;
    }

    private void decompile(Function function, DecompInterface decompiler) {
        if (function == null) {
            println("DECOMPILE function=none");
            return;
        }
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        println("DECOMPILE function=" + function.getName() + " entry=" +
            function.getEntryPoint() + " completed=" + result.decompileCompleted() +
            " error=" + result.getErrorMessage());
        if (result.getDecompiledFunction() != null) {
            println(result.getDecompiledFunction().getC());
        }
    }

    @Override
    public void run() throws Exception {
        long rootValue = rootAddress();
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only startup and bulk-copy caller report");
        if (rootValue < 0) {
            println("No configured root for this program");
            return;
        }

        Function root = currentProgram.getFunctionManager().getFunctionContaining(
            toAddr(rootValue));
        println("ROOT requested=" + toAddr(rootValue) + " function=" +
            (root == null ? "none" : root.getName() + "@" + root.getEntryPoint() +
                " body=" + root.getBody()));
        if (root != null) {
            for (Function called : root.getCalledFunctions(monitor)) {
                println("ROOT_CALLEE " + called.getName() + " entry=" +
                    called.getEntryPoint() + " body=" + called.getBody());
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            decompile(root, decompiler);

            if (currentProgram.getName().equals("app_candidate_b.bin")) {
                Address copyEntry = toAddr(0x1bdceL);
                Function copy = currentProgram.getFunctionManager().getFunctionAt(copyEntry);
                println("COPY_ROUTINE " + (copy == null ? "none" : copy.getName() +
                    " entry=" + copy.getEntryPoint() + " body=" + copy.getBody()));
                for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(
                        copyEntry)) {
                    Function caller = currentProgram.getFunctionManager().getFunctionContaining(
                        reference.getFromAddress());
                    println("COPY_CALL from=" + reference.getFromAddress() + " type=" +
                        reference.getReferenceType() + " caller=" +
                        (caller == null ? "none" : caller.getName() + "@" +
                            caller.getEntryPoint()));
                }
                decompile(copy, decompiler);
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
