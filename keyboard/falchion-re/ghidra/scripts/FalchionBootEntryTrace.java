// Read-only report tracing the application jump-to-bootloader magic/reset path
// back toward the Candidate B vendor-HID dispatcher. No device access.
// @category Falchion

import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class FalchionBootEntryTrace extends GhidraScript {
    private static final long[] VALUES = {
        0x20000ffcL, 0x73207320L, 0xe000ed0cL, 0x05fa0004L
    };

    private String fn(Function f) {
        return f == null ? "none" : f.getName() + "@" + f.getEntryPoint();
    }

    private void addRefFunctions(Address target, Set<Function> out) {
        ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(target);
        while (refs.hasNext()) {
            Reference ref = refs.next();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(
                ref.getFromAddress());
            println("  REF target=" + target + " from=" + ref.getFromAddress() +
                " type=" + ref.getReferenceType() + " function=" + fn(f));
            if (f != null) out.add(f);
        }
    }

    private void disassembleRange(long start, long end) {
        Listing listing = currentProgram.getListing();
        Address cursor = toAddr(start);
        println(String.format("DISASSEMBLY 0x%08x..0x%08x", start, end));
        while (cursor.getOffset() < end) {
            Instruction ins = listing.getInstructionAt(cursor);
            if (ins == null) {
                cursor = cursor.add(2);
                continue;
            }
            println("  " + cursor + "  " + ins);
            cursor = cursor.add(ins.getLength());
        }
    }

    private String bytes(Address start, int length) throws Exception {
        byte[] data = new byte[length];
        currentProgram.getMemory().getBytes(start, data);
        StringBuilder out = new StringBuilder();
        for (byte b : data) out.append(String.format("%02x ", b & 0xff));
        return out.toString().trim();
    }

    private void scanWord(long value, String label, Set<Function> out) throws Exception {
        Memory memory = currentProgram.getMemory();
        println(String.format("SCAN_WORD %s=0x%08x", label, value));
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            long start = (block.getStart().getOffset() + 3) & ~3L;
            long end = block.getEnd().getOffset();
            for (long p = start; p + 3 <= end; p += 4) {
                if (Integer.toUnsignedLong(memory.getInt(toAddr(p))) != value) continue;
                Address hit = toAddr(p);
                println("  WORD " + hit + " nearby=" + bytes(hit.subtract(8), 20));
                addRefFunctions(hit, out);
            }
        }
    }

    private void decompile(Function f, DecompInterface d, Set<Function> done) {
        if (f == null || !done.add(f)) return;
        Set<String> callers = new LinkedHashSet<>();
        for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(
                f.getEntryPoint())) {
            Function caller = currentProgram.getFunctionManager().getFunctionContaining(
                ref.getFromAddress());
            if (caller != null && !caller.equals(f)) callers.add(fn(caller));
        }
        println("DECOMPILE " + fn(f) + " body=" + f.getBody() + " callers=" + callers);
        DecompileResults result = d.decompileFunction(f, 120, monitor);
        if (result.getDecompiledFunction() != null) {
            println(result.getDecompiledFunction().getC());
        } else {
            println("  FAILED " + result.getErrorMessage());
        }
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline application jump-to-bootloader trace");
        if (!currentProgram.getName().equals("app_candidate_b_18000000.bin")) {
            println("need app_candidate_b_18000000.bin");
            return;
        }

        Memory memory = currentProgram.getMemory();
        FunctionManager fm = currentProgram.getFunctionManager();
        Set<Function> hits = new LinkedHashSet<>();

        for (long value : VALUES) {
            println(String.format("VALUE 0x%08x", value));
            for (MemoryBlock block : memory.getBlocks()) {
                if (!block.isInitialized()) continue;
                long start = (block.getStart().getOffset() + 3) & ~3L;
                long end = block.getEnd().getOffset();
                for (long p = start; p + 3 <= end; p += 4) {
                    if (Integer.toUnsignedLong(memory.getInt(toAddr(p))) != value) continue;
                    Address literal = toAddr(p);
                    println("LITERAL " + literal);
                    addRefFunctions(literal, hits);
                }
            }
        }

        long[] known = {0x18016464L, 0x18016468L, 0x18016470L, 0x1801835cL};
        for (long p : known) {
            println(String.format("KNOWN 0x%08x word=0x%08x", p,
                Integer.toUnsignedLong(memory.getInt(toAddr(p)))));
            addRefFunctions(toAddr(p), hits);
        }

        long[] inspect = {0x1801645cL, 0x18016460L, 0x18016464L, 0x18016468L,
            0x1801646cL, 0x18016470L, 0x18018358L, 0x1801835cL, 0x18018360L};
        for (long p : inspect) {
            long value = Integer.toUnsignedLong(memory.getInt(toAddr(p)));
            println(String.format("DATA 0x%08x value=0x%08x nearby=%s", p, value,
                bytes(toAddr(p), 24)));
            if (memory.contains(toAddr(value))) {
                println("  DEREF " + toAddr(value) + " bytes=" + bytes(toAddr(value), 24));
            }
        }

        // Cortex-M function pointers carry the Thumb bit in tables.
        scanWord(0x180160d9L, "FUN_180160d8_thumb", hits);
        scanWord(0x180160d8L, "FUN_180160d8_even", hits);
        scanWord(0x18017f55L, "FUN_18017f54_thumb", hits);
        scanWord(0x18017f54L, "FUN_18017f54_even", hits);

        Function dispatcher = fm.getFunctionContaining(toAddr(0x18001fbeL));
        disassembleRange(0x180039d0L, 0x18003a30L); // top-level 0xb0/reset branch

        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        Set<Function> done = new LinkedHashSet<>();
        try {
            for (Function f : hits) {
                if (f != null && !f.equals(dispatcher)) decompile(f, d, done);
            }
            Set<Function> callers = new LinkedHashSet<>();
            for (Function f : hits) {
                if (f == null) continue;
                for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(
                        f.getEntryPoint())) {
                    Function caller = fm.getFunctionContaining(ref.getFromAddress());
                    if (caller != null && !caller.equals(f)) callers.add(caller);
                }
            }
            for (Function f : callers) {
                if (f != null && !f.equals(dispatcher)) decompile(f, d, done);
            }
        } finally {
            d.dispose();
        }
        println("DONE hit_functions=" + hits.size());
    }
}
