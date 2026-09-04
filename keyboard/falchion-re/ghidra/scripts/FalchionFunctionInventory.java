// Per-function inventory for cross-release matching. Read-only: makes no change
// to the program database. Emits one machine-parseable line per function.
//
// Each function gets several independent signals so a match never rests on an
// address alone:
//   ranges     the function body's actual ordered address ranges; Ghidra
//              bodies are not necessarily contiguous and several here are not
//   bytes_sha  exact body bytes, concatenated across those ranges in address
//              order, never entry..entry+size
//   shape_sha  mnemonics plus operand kinds with every scalar and address
//              masked out, so relocated-but-identical code still matches
//   consts     sorted distinct scalar operands
//   callees    called function entry points, in address order
//   callers    number of calling functions
//   strings    string data referenced from the body
//
// @category Falchion
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.block.BasicBlockModel;
import ghidra.program.model.block.CodeBlock;
import ghidra.program.model.block.CodeBlockIterator;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.TreeSet;

public class FalchionFunctionInventory extends GhidraScript {

    private static String hex(byte[] digest) {
        StringBuilder text = new StringBuilder();
        for (byte value : digest) {
            text.append(String.format("%02x", value));
        }
        return text.toString();
    }

    private static String sha256(byte[] data) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(data));
    }

    /** Mnemonic plus operand kinds, with scalars and addresses masked out. */
    private String shapeOf(Instruction instruction) {
        StringBuilder shape = new StringBuilder(instruction.getMnemonicString());
        for (int index = 0; index < instruction.getNumOperands(); index++) {
            shape.append(' ');
            Object[] parts = instruction.getOpObjects(index);
            if (parts.length == 0) {
                shape.append('?');
            }
            for (Object part : parts) {
                if (part instanceof Scalar) {
                    shape.append("#S");
                } else if (part instanceof Address) {
                    shape.append("#A");
                } else {
                    shape.append(part.toString());
                }
            }
        }
        return shape.toString();
    }

    @Override
    public void run() throws Exception {
        Listing listing = currentProgram.getListing();
        BasicBlockModel blockModel = new BasicBlockModel(currentProgram);

        println("PROGRAM " + currentProgram.getName());
        println("IMAGE_BASE " + currentProgram.getImageBase());
        println("LANGUAGE " + currentProgram.getLanguageID());
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            println("BLOCK " + block.getName() + " " + block.getStart() + " "
                + block.getEnd() + " size=0x" + Long.toHexString(block.getSize()));
        }

        List<String> lines = new ArrayList<>();
        FunctionIterator functions = currentProgram.getFunctionManager()
            .getFunctions(true);
        int total = 0;
        while (functions.hasNext()) {
            Function function = functions.next();
            if (function.isExternal() || function.isThunk()) {
                continue;
            }
            total++;
            AddressSetView body = function.getBody();

            StringBuilder shapes = new StringBuilder();
            TreeSet<Long> constants = new TreeSet<>();
            TreeSet<String> strings = new TreeSet<>();
            int instructionCount = 0;
            InstructionIterator instructions = listing.getInstructions(body, true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                instructionCount++;
                shapes.append(shapeOf(instruction)).append('\n');
                for (int index = 0; index < instruction.getNumOperands(); index++) {
                    for (Object part : instruction.getOpObjects(index)) {
                        if (part instanceof Scalar) {
                            constants.add(((Scalar) part).getUnsignedValue());
                        }
                    }
                }
                for (Reference reference : instruction.getReferencesFrom()) {
                    Data data = listing.getDataAt(reference.getToAddress());
                    if (data != null && data.hasStringValue()) {
                        strings.add(data.getValue().toString()
                            .replace("\\", "\\\\").replace("|", "\\|")
                            .replace("\n", "\\n").replace(" ", "\\s"));
                    }
                }
            }

            // Bodies can be discontiguous, and in this firmware several are.
            // Read each real range and hash the concatenation in address order.
            List<String> rangeText = new ArrayList<>();
            java.io.ByteArrayOutputStream bodyStream =
                new java.io.ByteArrayOutputStream();
            for (AddressRange range : body.getAddressRanges(true)) {
                long length = range.getLength();
                byte[] chunk = new byte[(int) length];
                currentProgram.getMemory().getBytes(range.getMinAddress(), chunk);
                bodyStream.write(chunk);
                rangeText.add(range.getMinAddress() + "-"
                    + range.getMaxAddress().add(1));
            }
            byte[] bodyBytes = bodyStream.toByteArray();

            int blocks = 0;
            CodeBlockIterator blockIterator =
                blockModel.getCodeBlocksContaining(body, monitor);
            while (blockIterator.hasNext()) {
                blockIterator.next();
                blocks++;
            }

            List<String> callees = new ArrayList<>();
            for (Function callee : function.getCalledFunctions(monitor)) {
                callees.add(callee.getEntryPoint().toString());
            }
            Collections.sort(callees);

            List<String> constantText = new ArrayList<>();
            for (Long value : constants) {
                constantText.add("0x" + Long.toHexString(value));
            }

            lines.add("FUNC"
                + " entry=" + function.getEntryPoint()
                + " name=" + function.getName()
                + " size=0x" + Long.toHexString(body.getNumAddresses())
                + " ranges=" + String.join(";", rangeText)
                + " insns=" + instructionCount
                + " blocks=" + blocks
                + " bytes_sha=" + sha256(bodyBytes)
                + " shape_sha=" + sha256(shapes.toString().getBytes("UTF-8"))
                + " callers=" + function.getCallingFunctions(monitor).size()
                + " callees=" + String.join(",", callees)
                + " consts=" + String.join(",", constantText)
                + " strings=" + String.join(",", strings));
        }
        Collections.sort(lines);
        for (String line : lines) {
            println(line);
        }
        println("RESULT functions=" + total);
    }
}
