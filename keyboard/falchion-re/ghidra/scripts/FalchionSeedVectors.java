// Create functions at exception and interrupt handler entry points.
//
// A raw binary import gives Ghidra no reason to treat a vector-table word as a
// code reference, so handlers that are only ever reached through the table are
// left undisassembled and absent from the function list. That makes any
// reachability analysis out of the vector table come back empty, and leaves the
// fault, SysTick, PendSV and interrupt handlers unanalysed.
//
// This script only ever adds a label and a function at an address the caller
// supplies; it changes nothing else, and it never touches a source dump. It is
// intended for the ignored ghidra/project-step6 database.
//
// Arguments: one or more name=address pairs, address in hex with or without a
// leading 0x and with the Thumb bit already stripped. An address outside the
// program, or one that already has a function, is reported and skipped.
//
// @category Falchion
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class FalchionSeedVectors extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        println("PROGRAM " + currentProgram.getName());
        if (args.length == 0) {
            println("RESULT created=0 error=no name=address pairs supplied");
            return;
        }

        int created = 0;
        int existing = 0;
        int skipped = 0;
        for (String pair : args) {
            int split = pair.indexOf('=');
            if (split <= 0) {
                println("SKIP " + pair + " reason=not_a_name_equals_address_pair");
                skipped++;
                continue;
            }
            String name = pair.substring(0, split);
            String text = pair.substring(split + 1).replaceFirst("^0[xX]", "");
            Address address;
            try {
                address = currentProgram.getAddressFactory()
                    .getDefaultAddressSpace().getAddress(Long.parseLong(text, 16));
            } catch (NumberFormatException exception) {
                println("SKIP " + pair + " reason=unparseable_address");
                skipped++;
                continue;
            }
            if (!currentProgram.getMemory().contains(address)) {
                println("SKIP " + name + "@" + address
                    + " reason=outside_this_program");
                skipped++;
                continue;
            }

            Function already = getFunctionAt(address);
            if (already != null) {
                println("EXISTING " + name + "@" + address + " as "
                    + already.getName());
                existing++;
                continue;
            }

            disassemble(address);
            Function function = createFunction(address, name);
            if (function == null) {
                println("SKIP " + name + "@" + address
                    + " reason=createFunction_returned_null");
                skipped++;
                continue;
            }
            createLabel(address, name, true, SourceType.USER_DEFINED);
            println("CREATED " + name + "@" + address);
            created++;
        }
        println("RESULT created=" + created + " existing=" + existing
            + " skipped=" + skipped);
    }
}
