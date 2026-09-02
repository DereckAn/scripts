// Read-only report of the bootloader integrity/verify path.
// Decodes the SN_FWIN boot-selection chain and the two checksum routines:
//   FUN_00005028  per-record checksum = sum of per-0x10000-chunk IEEE CRC-32
//   FUN_000026d0  whole-region additive 32-bit word-sum (terminal values)
// @category Falchion

import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderVerifyReport extends GhidraScript {

    // Verify-path cluster reached from the boot orchestrator FUN_00007ec8.
    private static final long[] ENTRIES = {
        0x7ec8L,  // boot orchestrator: selects candidate, word-sum-checks, jumps
        0x2af0L,  // FUN_00008000(0x60000000) wrapper (boot-priority selector)
        0x8000L,  // scans SN_FWIN headers, verifies magic + records, returns entry
        0x511cL,  // per-record CRC verifier loop (compares record.crc at +0x2c)
        0x5028L,  // per-record checksum: sum of per-0x10000-chunk CRC-32
        0x28e8L,  // hardware CRC engine setup (mode 5)
        0x5240L,  // fw_info entry-address range check
        0x26d0L,  // whole-region additive word-sum verifier
    };
    // Header base literal 0x60010000 in the slice.
    private static final long HDR_LITERAL = 0x277cL;

    private String fn(Function f) {
        return f == null ? "none" : f.getName() + "@" + f.getEntryPoint();
    }

    private Set<String> callersOf(Function function) {
        Set<String> callers = new LinkedHashSet<>();
        for (Reference ref : currentProgram.getReferenceManager()
                .getReferencesTo(function.getEntryPoint())) {
            Function c = currentProgram.getFunctionManager()
                .getFunctionContaining(ref.getFromAddress());
            if (c != null && !c.equals(function)) callers.add(fn(c));
        }
        return callers;
    }

    private void decompile(Function f, DecompInterface dec, Set<Function> done) {
        if (f == null || !done.add(f)) return;
        println("DECOMPILE " + fn(f) + " body=" + f.getBody()
            + " callers=" + callersOf(f));
        DecompileResults r = dec.decompileFunction(f, 120, monitor);
        println("  completed=" + r.decompileCompleted() + " error=" + r.getErrorMessage());
        if (r.getDecompiledFunction() != null) println(r.getDecompiledFunction().getC());
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only bootloader integrity/verify path report");
        if (!currentProgram.getName().equals("bootloader_primary.bin")) {
            println("This report requires bootloader_primary.bin");
            return;
        }

        Address lit = toAddr(HDR_LITERAL);
        println(String.format("HDR_LITERAL @%s = 0x%08x", lit,
            Integer.toUnsignedLong(currentProgram.getMemory().getInt(lit))));
        for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(lit)) {
            Function f = currentProgram.getFunctionManager()
                .getFunctionContaining(ref.getFromAddress());
            println("  hdr_ref from=" + ref.getFromAddress() + " fn=" + fn(f));
        }

        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        Set<Function> done = new LinkedHashSet<>();
        try {
            for (long e : ENTRIES) {
                Function f = currentProgram.getFunctionManager()
                    .getFunctionContaining(toAddr(e));
                if (f == null) {
                    println("NO_FUNCTION_AT 0x" + Long.toHexString(e));
                    continue;
                }
                decompile(f, dec, done);
            }
        } finally {
            dec.dispose();
        }
        println("DONE decompiled=" + done.size());
    }
}
