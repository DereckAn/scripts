// Read-only report: map bootloader vendor-HID callback channel 0 to its USB
// interface and endpoint descriptors. Uses only the offline Ghidra program.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderInterfaceMap extends GhidraScript {
    private String fn(Function f) {
        return f == null ? "none" : f.getName() + "@" + f.getEntryPoint();
    }

    private void refs(long address) {
        Address target = toAddr(address);
        StringBuilder line = new StringBuilder(String.format("REFS 0x%08x", address));
        boolean any = false;
        for (Reference ref : currentProgram.getReferenceManager().getReferencesTo(target)) {
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            line.append(String.format(" %s<-%s", ref.getFromAddress(), fn(owner)));
            any = true;
        }
        if (!any) line.append(" none");
        println(line.toString());
    }

    private void words(long start, long end) throws Exception {
        Memory memory = currentProgram.getMemory();
        for (long address = start; address < end; address += 16) {
            StringBuilder line = new StringBuilder(String.format("0x%08x", address));
            for (int index = 0; index < 4 && address + index * 4 < end; index++) {
                line.append(String.format(" %08x",
                    Integer.toUnsignedLong(memory.getInt(toAddr(address + index * 4)))));
            }
            println(line.toString());
        }
    }

    private void findWords(long... values) throws Exception {
        Memory memory = currentProgram.getMemory();
        Set<Long> wanted = new LinkedHashSet<>();
        for (long value : values) wanted.add(value);
        for (ghidra.program.model.mem.MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            long start = (block.getStart().getOffset() + 3) & ~3L;
            long end = block.getEnd().getOffset();
            for (long address = start; address + 3 <= end; address += 4) {
                long value = Integer.toUnsignedLong(memory.getInt(toAddr(address)));
                if (wanted.contains(value)) {
                    println(String.format("WORD 0x%08x = 0x%08x", address, value));
                }
            }
        }
    }

    private byte[] reconstructInitializedRam(long prefixSource, int prefixLength,
                                             long source, int length) throws Exception {
        Memory memory = currentProgram.getMemory();
        int lowerRamWindow = 0x1000;
        byte[] output = new byte[lowerRamWindow + prefixLength + length];
        for (int index = 0; index < prefixLength; index++) {
            output[lowerRamWindow + index] = memory.getByte(toAddr(prefixSource + index));
        }
        int sourceOffset = 0;
        int outputOffset = lowerRamWindow + prefixLength;
        int outputEnd = lowerRamWindow + prefixLength + length;
        int token = 0;
        int control = memory.getByte(toAddr(source + sourceOffset++)) & 0xff;
        while (outputOffset < outputEnd) {
            int tokenSource = sourceOffset - 1;
            int tokenOutput = outputOffset;
            int literalCode = control & 3;
            if (literalCode == 0) {
                literalCode = memory.getByte(toAddr(source + sourceOffset++)) & 0xff;
            }
            int literalCount = literalCode - 1;
            for (int index = 0; index < literalCount && outputOffset < outputEnd; index++) {
                output[outputOffset++] = memory.getByte(toAddr(source + sourceOffset++));
            }

            int matchCode = control >>> 4;
            if (matchCode == 0) {
                matchCode = memory.getByte(toAddr(source + sourceOffset++)) & 0xff;
            }
            if (matchCode != 0) {
                int distance = memory.getByte(toAddr(source + sourceOffset++)) & 0xff;
                if ((control & 0x0c) == 0x0c) {
                    distance += (memory.getByte(toAddr(source + sourceOffset++)) & 0xff) << 8;
                } else {
                    distance += (control & 0x0c) << 6;
                }
                int matchOffset = outputOffset - distance;
                int matchCount = matchCode + 2;
                if (matchOffset < 0) {
                    throw new IllegalStateException(String.format(
                        "invalid back-reference token=%d control=0x%02x source+0x%x output=0x%x distance=0x%x literals=%d match=%d",
                        token, control, tokenSource, tokenOutput, distance, literalCount, matchCount));
                }
                for (int index = 0; index < matchCount && outputOffset < outputEnd; index++) {
                    output[outputOffset++] = output[matchOffset++];
                }
            }
            if (outputOffset < outputEnd) {
                control = memory.getByte(toAddr(source + sourceOffset++)) & 0xff;
            }
            token++;
        }
        println(String.format("DECOMPRESSED source=0x%08x consumed=0x%x output=0x%x lower_zero_window=0x%x",
            source, sourceOffset, outputOffset, lowerRamWindow));
        return output;
    }

    private void dumpRam(byte[] data, long ramBase, long start, long end) {
        for (long address = start; address < end; address += 16) {
            StringBuilder line = new StringBuilder(String.format("RAM 0x%08x", address));
            for (int index = 0; index < 16 && address + index < end; index++) {
                int offset = (int)(address + index - ramBase);
                line.append(String.format(" %02x", data[offset] & 0xff));
            }
            println(line.toString());
        }
    }

    private void findBytes(byte[] data, long ramBase, String label, int... pattern) {
        for (int offset = 0; offset + pattern.length <= data.length; offset++) {
            boolean match = true;
            for (int index = 0; index < pattern.length; index++) {
                if ((data[offset + index] & 0xff) != pattern[index]) {
                    match = false;
                    break;
                }
            }
            if (match) println(String.format("FOUND %s at RAM 0x%08x", label, ramBase + offset));
        }
    }

    private void pdis(long start, long end) {
        PseudoDisassembler disassembler = new PseudoDisassembler(currentProgram);
        Address address = toAddr(start);
        while (address.getOffset() < end) {
            try {
                Instruction existing = currentProgram.getListing().getInstructionAt(address);
                if (existing != null) {
                    println(String.format("%s  %s", address, existing));
                    address = address.add(existing.getLength());
                    continue;
                }
                PseudoInstruction instruction = disassembler.disassemble(address);
                if (instruction == null) {
                    println(address + "  (undecodable)");
                    address = address.add(2);
                    continue;
                }
                println(String.format("%s  %s", address, instruction));
                address = address.add(instruction.getLength());
            } catch (Exception exception) {
                println(address + "  (error " + exception.getMessage() + ")");
                address = address.add(2);
            }
        }
    }

    private void decompile(DecompInterface decompiler, long address) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(toAddr(address));
        if (function == null) {
            println(String.format("NOFUNC 0x%08x", address));
            return;
        }
        println("DECOMPILE " + fn(function));
        DecompileResults results = decompiler.decompileFunction(function, 120, monitor);
        if (results.getDecompiledFunction() != null) {
            println(results.getDecompiledFunction().getC());
        }
    }

    private void decompileDirectCallees(DecompInterface decompiler, long address) {
        Function root = currentProgram.getFunctionManager().getFunctionContaining(toAddr(address));
        if (root == null) {
            println(String.format("NOFUNC 0x%08x", address));
            return;
        }
        println("CALL_ROOT " + fn(root));
        Set<Function> callees = new TreeSet<>(Comparator.comparing(f -> f.getEntryPoint().getOffset()));
        callees.addAll(root.getCalledFunctions(monitor));
        for (Function callee : callees) {
            println("DIRECT_CALLEE " + fn(callee));
            decompile(decompiler, callee.getEntryPoint().getOffset());
        }
    }

    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only map: router callback channel -> USB interface/endpoints");
        if (!currentProgram.getName().equals("bootloader_primary.bin")) {
            println("need bootloader_primary.bin");
            return;
        }

        println("=== A: references to report descriptor and nearby data ===");
        long[] targets = {0xce48L, 0xce5bL, 0xce7cL, 0xc130L, 0xbfb8L, 0xbf04L, 0xbc10L};
        for (long target : targets) refs(target);

        println("=== B: callback/class setup disassembly ===");
        pdis(0xb0c0L, 0xb180L);
        pdis(0xbd00L, 0xbe20L);
        pdis(0xbef0L, 0xc180L);

        println("=== C: callback/class setup decompilation ===");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            long[] functions = {0x7db4L, 0xb0d0L, 0xb104L, 0xb110L, 0xb124L,
                                0xb130L, 0xbd40L, 0xbd90L, 0xbfc8L, 0xbf14L,
                                0xc120L, 0x7764L, 0x77e4L};
            Set<Function> seen = new LinkedHashSet<>();
            for (long address : functions) {
                Function function = currentProgram.getFunctionManager().getFunctionContaining(toAddr(address));
                if (function != null && seen.add(function)) decompile(decompiler, address);
                else if (function == null) println(String.format("NOFUNC 0x%08x", address));
            }
        } finally {
            decompiler.dispose();
        }

        println("=== D: likely USB class/configuration constant area ===");
        words(0xbc00L, 0xc180L);
        words(0xce40L, 0xd100L);

        println("=== E: general USB initializer and direct callees ===");
        decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            decompile(decompiler, 0x4ec8L);
            decompileDirectCallees(decompiler, 0x4ec8L);
        } finally {
            decompiler.dispose();
        }

        println("=== F: HID/channel endpoint registration ===");
        findWords(0x7765L, 0x77e5L, 0x76adL, 0x744dL, 0x7555L,
                  0x7605L, 0x7659L, 0x73f9L, 0x7501L);
        decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            long[] functions = {0xa364L, 0xbcacL, 0x73f8L, 0x744cL, 0x7500L,
                                0x7554L, 0x7604L, 0x7658L, 0x76acL, 0x7764L};
            for (long address : functions) decompile(decompiler, address);
            decompileDirectCallees(decompiler, 0xbcacL);
            decompileDirectCallees(decompiler, 0xa364L);
        } finally {
            decompiler.dispose();
        }
        println("=== G: scatter-load decompressor ===");
        pdis(0x17cL, 0x1e0L);

        println("=== H: reconstructed initialized RAM and descriptor locations ===");
        long ramBase = 0x1800f000L;
        byte[] initialized = reconstructInitializedRam(0xcdfcL, 0x50, 0xce4cL, 0x1118);
        findBytes(initialized, ramBase, "FF01 report", 0x06,0x01,0xff,0x09,0x01,0xa1,0x01);
        findBytes(initialized, ramBase, "FF00 report", 0x06,0x00,0xff,0x09,0x01,0xa1,0x01);
        findBytes(initialized, ramBase, "mouse report", 0x05,0x01,0x09,0x02,0xa1,0x01);
        findBytes(initialized, ramBase, "keyboard report", 0x05,0x01,0x09,0x06,0xa1,0x01);
        findBytes(initialized, ramBase, "configuration descriptor", 0x09,0x02);
        dumpRam(initialized, ramBase, 0x18010330L, 0x18010360L);
        dumpRam(initialized, ramBase, 0x18010620L, 0x18010820L);
        dumpRam(initialized, ramBase, 0x18010890L, 0x18010c20L);
        println("DONE");
    }
}
