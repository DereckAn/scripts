// Read-only report of direct references to Candidate B key-configuration RAM.
// @category Falchion

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

public class FalchionRamTableReferences extends GhidraScript {
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
        new Region("unsupported_key_lists", 0x1801c810L, 0x1801c90bL),
        new Region("profile_state", 0x1801ee64L, 0x1801ee80L),
        new Region("dirty_flags", 0x1801e68dL, 0x1801e700L),
        new Region("key_records", 0x18021db4L, 0x18022ca3L),
        new Region("threshold_table", 0x18024ee0L, 0x18025000L),
        new Region("vendor_hid_buffer", 0x1802337cL, 0x180233bbL)
    };

    private Region containingRegion(Address address) {
        long value = address.getOffset();
        for (Region region : REGIONS) {
            if (value >= region.start && value <= region.end) {
                return region;
            }
        }
        return null;
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        println("PURPOSE offline read-only direct-reference report; no device access and no project mutation");
        for (Region region : REGIONS) {
            println(String.format("REGION %s 0x%08x..0x%08x", region.name,
                region.start, region.end));
        }

        int count = 0;
        for (Instruction instruction : currentProgram.getListing().getInstructions(true)) {
            for (Reference reference : instruction.getReferencesFrom()) {
                Region region = containingRegion(reference.getToAddress());
                if (region == null) {
                    continue;
                }
                Function function = currentProgram.getFunctionManager().getFunctionContaining(
                    instruction.getAddress());
                println("REFERENCE region=" + region.name + " from=" +
                    instruction.getAddress() + " to=" + reference.getToAddress() +
                    " type=" + reference.getReferenceType() + " function=" +
                    (function == null ? "none" : function.getName() + "@" +
                        function.getEntryPoint()) + " instruction=" + instruction);
                count++;
            }
        }
        println("REFERENCE_COUNT " + count);
    }
}
