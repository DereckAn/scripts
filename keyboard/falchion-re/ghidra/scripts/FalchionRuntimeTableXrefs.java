// Read-only incoming-reference report for Candidate B runtime key tables.
// @category Falchion

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class FalchionRuntimeTableXrefs extends GhidraScript {
    private static class Region {
        String name;
        long start;
        long end;

        Region(String name, long start, long end) {
            this.name = name;
            this.start = start;
            this.end = end;
        }
    }

    private static final Region[] REGIONS = {
        new Region("key_translation", 0x1801bff6L, 0x1801c0b2L),
        new Region("wire_map_before_shared_overlap", 0x1801c37cL, 0x1801c50dL),
        new Region("shared_wire_scan_overlap", 0x1801c50eL, 0x1801c544L),
        new Region("scan_position_map_after_overlap", 0x1801c545L, 0x1801c80dL),
        new Region("unsupported_key_lists", 0x1801c810L, 0x1801c90bL)
    };

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only incoming xrefs, including literal/data references");

        int total = 0;
        for (Region region : REGIONS) {
            int regionCount = 0;
            println(String.format("REGION %s 0x%08x..0x%08x", region.name,
                region.start, region.end));
            for (long value = region.start; value <= region.end; value++) {
                Address target = toAddr(value);
                for (Reference reference : currentProgram.getReferenceManager().getReferencesTo(
                        target)) {
                    Address from = reference.getFromAddress();
                    Function function = currentProgram.getFunctionManager().getFunctionContaining(
                        from);
                    CodeUnit codeUnit = currentProgram.getListing().getCodeUnitContaining(from);
                    println("XREF region=" + region.name + " target=" + target +
                        " from=" + from + " type=" + reference.getReferenceType() +
                        " function=" + (function == null ? "none" : function.getName() +
                            "@" + function.getEntryPoint()) + " code=" +
                        (codeUnit == null ? "none" : codeUnit.toString()));
                    regionCount++;
                    total++;
                }
            }
            println("REGION_XREF_COUNT " + region.name + " " + regionCount);
        }
        println("TOTAL_XREF_COUNT " + total);
    }
}
