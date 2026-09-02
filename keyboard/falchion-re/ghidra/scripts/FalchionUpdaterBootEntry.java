// Read-only report for the native ASUS updater's application-to-bootloader step.
// No executable or USB/device access.
// @category Falchion

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class FalchionUpdaterBootEntry extends GhidraScript {
    private String fn(Function f) {
        return f == null ? "none" : f.getName() + "@" + f.getEntryPoint();
    }

    private void addRefs(Address target, Set<Function> functions) {
        ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(target);
        while (refs.hasNext()) {
            Reference ref = refs.next();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(
                ref.getFromAddress());
            println("  REF target=" + target + " from=" + ref.getFromAddress() +
                " type=" + ref.getReferenceType() + " function=" + fn(f));
            if (f != null) functions.add(f);
        }
    }

    private Set<Function> findBytes(String label, byte[] needle) {
        Memory memory = currentProgram.getMemory();
        Set<Function> functions = new LinkedHashSet<>();
        println("SEARCH " + label);
        Address cursor = memory.getMinAddress();
        while (cursor != null) {
            Address hit = memory.findBytes(cursor, needle, null, true, monitor);
            if (hit == null) break;
            println("  HIT " + hit);
            addRefs(hit, functions);
            cursor = hit.next();
        }
        return functions;
    }

    private void decompile(Function f, DecompInterface decompiler,
            Set<Function> done) {
        if (f == null || !done.add(f)) return;
        Set<String> callers = new LinkedHashSet<>();
        for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(
                f.getEntryPoint())) {
            Function caller = currentProgram.getFunctionManager().getFunctionContaining(
                ref.getFromAddress());
            if (caller != null && !caller.equals(f)) callers.add(fn(caller));
        }
        println("DECOMPILE " + fn(f) + " body=" + f.getBody() + " callers=" + callers);
        DecompileResults result = decompiler.decompileFunction(f, 180, monitor);
        if (result.getDecompiledFunction() != null) {
            println(result.getDecompiledFunction().getC());
        } else {
            println("  FAILED " + result.getErrorMessage());
        }
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline native-updater boot-entry trace");
        if (!currentProgram.getName().equals("peripheral_fwu_pro.exe")) {
            println("need peripheral_fwu_pro.exe");
            return;
        }

        Set<Function> roots = new LinkedHashSet<>();
        roots.addAll(findBytes("Jump to Bootloader",
            "Jump to Bootloader\0".getBytes(StandardCharsets.US_ASCII)));
        roots.addAll(findBytes("Entry Bootloader Success",
            "Entry Bootloader Success!\0".getBytes(StandardCharsets.US_ASCII)));
        roots.addAll(findBytes("ASUS boot frame",
            new byte[] {0x7b, (byte)0xaa, 0x41, 0x53, 0x55, 0x53, (byte)0xaa}));

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        Set<Function> done = new LinkedHashSet<>();
        try {
            // The string xrefs live in one enormous update routine. Its compact
            // boot-entry block calls these bounded packet-builder/transport helpers.
            long[] targets = {0x004054e0L, 0x00401b30L, 0x0040f4b0L};
            for (long target : targets) {
                decompile(currentProgram.getFunctionManager().getFunctionContaining(
                    toAddr(target)), decompiler, done);
            }
        } finally {
            decompiler.dispose();
        }
        println("DONE roots=" + roots.size());
    }
}
