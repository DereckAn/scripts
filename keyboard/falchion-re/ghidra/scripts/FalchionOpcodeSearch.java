// Read-only search for functions using constants from the recorded vendor-HID protocol.
// @category Falchion

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class FalchionOpcodeSearch extends GhidraScript {
    private static final long[] TARGETS = {
        0x12L, 0x21L, 0x50L, 0x51L, 0x55L, 0x9fL, 0x2151L, 0x5550L
    };

    private boolean isTarget(long value) {
        for (long target : TARGETS) {
            if (value == target) {
                return true;
            }
        }
        return false;
    }

    private String hex(long value) {
        return String.format("0x%x", value);
    }

    private Set<String> callersOf(Function function) {
        Set<String> callers = new LinkedHashSet<>();
        ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(
            function.getEntryPoint());
        while (refs.hasNext()) {
            Reference ref = refs.next();
            Function caller = currentProgram.getFunctionManager().getFunctionContaining(
                ref.getFromAddress());
            if (caller != null && !caller.equals(function)) {
                callers.add(caller.getName() + "@" + caller.getEntryPoint());
            }
        }
        return callers;
    }

    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("app_candidate_b.bin")) {
            println("This search is scoped to app_candidate_b.bin; current=" +
                currentProgram.getName());
            return;
        }

        Address rawPair = toAddr(0x2c16L);
        Function rawPairFunction = currentProgram.getFunctionManager().getFunctionContaining(rawPair);
        println("PROGRAM " + currentProgram.getName());
        println("raw_51_21_pair_address=" + rawPair + " containing_function=" +
            (rawPairFunction == null ? "none" : rawPairFunction.getName() + "@" +
                rawPairFunction.getEntryPoint()));

        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        int reported = 0;
        while (functions.hasNext()) {
            Function function = functions.next();
            Map<Long, List<String>> hits = new LinkedHashMap<>();
            InstructionIterator instructions = currentProgram.getListing().getInstructions(
                function.getBody(), true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) {
                            continue;
                        }
                        long value = ((Scalar) object).getUnsignedValue();
                        if (!isTarget(value)) {
                            continue;
                        }
                        hits.computeIfAbsent(value, ignored -> new ArrayList<>()).add(
                            instruction.getAddress() + " " + instruction.toString());
                    }
                }
            }

            boolean has51Pair = hits.containsKey(0x51L) && hits.containsKey(0x21L);
            boolean has50Pair = hits.containsKey(0x50L) && hits.containsKey(0x55L);
            boolean hasCombined = hits.containsKey(0x2151L) || hits.containsKey(0x5550L);
            boolean containsRawPair = function.getBody().contains(rawPair);
            boolean broadMatch = hits.size() >= 5;
            if (!(has51Pair || has50Pair || hasCombined || containsRawPair || broadMatch)) {
                continue;
            }

            reported++;
            println("FUNCTION " + function.getName() + " entry=" + function.getEntryPoint() +
                " body=" + function.getBody() + " callers=" + callersOf(function));
            for (Map.Entry<Long, List<String>> entry : hits.entrySet()) {
                println("  constant=" + hex(entry.getKey()));
                for (String hit : entry.getValue()) {
                    println("    " + hit);
                }
            }
        }
        println("reported_function_count=" + reported);
    }
}
