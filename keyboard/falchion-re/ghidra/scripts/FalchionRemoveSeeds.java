// SUPERSEDED AND INERT — see logs 132 and 133. This script mutates nothing.
//
// WHAT IT USED TO DO, and why that was wrong. It removed a function that had
// been seeded from a pointer-table candidate later shown to be a false
// positive, then called clearListing() on the function's body, on the
// assumption that auto-analysis would rebuild the real code underneath. IT
// DOES NOT. A routine that nothing in the image references is never
// disassembled, so clearing it DELETES it. Running this in log 131 destroyed
// the real routine at 0x000009fc..0x00000a46 and, with it, the write of 0x3f
// to 0xe000ef00 at 0x00000a26; it also left FUN_00003dd8 ending mid-epilogue
// at 0x4004 and reduced the 0x40b2 long-branch veneer to a one-byte function.
//
// A banner alone was not enough: log 133 observed that run() still called
// removeFunction(), symbol.delete() and clearListing(), so one accidental
// invocation could repeat the damage. Every destructive call is now gone from
// this file — not commented out, not behind a flag. The imports the mutating
// version needed are gone too, so a copy-paste restoration cannot compile by
// accident.
//
// THE CORRECT PROCEDURE, which log 132 used:
//   1. ghidra-analyzeHeadless <project> <name> -import <slice> \
//        -processor ARM:LE:32:Cortex -loader BinaryLoader \
//        -loader-baseAddr <base> -overwrite
//   2. re-analyse
//   3. replay ONLY the legitimate seeds, in their historical order, with a
//      re-analysis after each group (log 100 vectors, log 106 task entry,
//      log 118 EA_cand_*), omitting the false ones
//   4. define any verified orphan routine explicitly at a boundary read off
//      the instruction stream, and check it with FalchionSpanReport.java
//   5. regenerate the inventories and peripheral maps read-only
//
// This file is kept so the reproduction trail in logs 131 and 132 can be
// followed. History does not need an executable hazard to stay reproducible.
//
// @category Falchion
import ghidra.app.script.GhidraScript;

public class FalchionRemoveSeeds extends GhidraScript {

    @Override
    public void run() throws Exception {
        println("REFUSED FalchionRemoveSeeds is superseded and inert.");
        println("REASON removing a function and clearing its body does not let");
        println("REASON auto-analysis rebuild the code underneath; when nothing");
        println("REASON references that code, clearing it deletes it. Log 131 lost");
        println("REASON the routine at 0x000009fc and the 0xe000ef00 write at");
        println("REASON 0x00000a26 that way, and split FUN_00003dd8 at 0x4004.");
        println("INSTEAD re-import the program and replay only the legitimate");
        println("INSTEAD seeds; see log 132 for the exact sequence, and check the");
        println("INSTEAD result with FalchionSpanReport.java.");
        println("RESULT removed=0 refused=1 mutated=0");
    }
}
