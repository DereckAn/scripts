// Report, for each address given, whether it is defined code and what owns it.
//
// Log 131 removed three functions that had been seeded from two false pointer
// tables, and cleared their bodies expecting reanalysis to restore the real
// code underneath. It did not: a routine that nothing references is never
// disassembled, so genuine instructions and a genuine peripheral access went
// missing. Log 132 rebuilds the entry images and repairs the spans explicitly,
// and this script is the check that the repair actually landed — it is the
// evidence for "no repaired code span remains undefined", and it is the only
// way to see a THUNK, which FalchionFunctionInventory deliberately skips.
//
// Arguments: addresses in hex, optionally as `lo-hi` to report a whole span.
//
// @category Falchion
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class FalchionSpanReport extends GhidraScript {

    private Address at(String text) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
            .getAddress(Long.parseLong(text.replaceFirst("^0[xX]", ""), 16));
    }

    private void report(Address address) {
        CodeUnit unit = currentProgram.getListing().getCodeUnitContaining(address);
        String kind;
        if (unit instanceof Instruction) {
            kind = "instruction " + unit.getMinAddress() + " " + unit;
        } else if (unit instanceof Data && ((Data) unit).isDefined()) {
            kind = "data " + unit.getMinAddress();
        } else {
            kind = "UNDEFINED";
        }
        Function owner = getFunctionContaining(address);
        String function = owner == null ? "none"
            : owner.getName() + "@" + owner.getEntryPoint()
              + (owner.isThunk() ? " THUNK->" + owner.getThunkedFunction(true).getName() : "")
              + " body=" + owner.getBody();
        println("SPAN " + address + " " + kind + " | function=" + function);
    }

    @Override
    public void run() throws Exception {
        println("PROGRAM " + currentProgram.getName());
        int undefined = 0;
        int total = 0;
        for (String argument : getScriptArgs()) {
            if (argument.contains("-")) {
                String[] parts = argument.split("-");
                Address low = at(parts[0]);
                Address high = at(parts[1]);
                for (Address cursor = low; cursor.compareTo(high) < 0;) {
                    CodeUnit unit = currentProgram.getListing()
                        .getCodeUnitContaining(cursor);
                    total++;
                    if (!(unit instanceof Instruction)) {
                        undefined++;
                        report(cursor);
                        cursor = cursor.add(2);
                        continue;
                    }
                    report(cursor);
                    cursor = unit.getMaxAddress().add(1);
                }
            } else {
                total++;
                Address address = at(argument);
                if (!(currentProgram.getListing().getCodeUnitContaining(address)
                        instanceof Instruction)) {
                    undefined++;
                }
                report(address);
            }
        }
        println("RESULT reported=" + total + " undefined=" + undefined);
    }
}
