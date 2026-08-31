// Read-only report of the bootloader (PID 1b7f) vendor-HID WIRE FRAMING:
// the 64-byte report router, the OUT sub-command parser, the IN/query responder,
// and the force-bootloader flag check. Prints the HID report descriptor bytes and
// the force-boot flag/magic literals. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address; import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
public class FalchionBootloaderFraming extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only bootloader vendor-HID wire-framing report");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory();
        // HID report descriptor (vendor usage page 0xFF01) at 0xce5b
        StringBuilder hd=new StringBuilder("HID_REPORT_DESCRIPTOR @0xce5b:");
        for(int i=0;i<40;i++) hd.append(String.format(" %02x", m.getByte(toAddr(0xce5bL+i))&0xff));
        println(hd.toString());
        // force-bootloader flag address + magic (checked by FUN_00002a44)
        println(String.format("FORCE_BOOT flag_addr=0x%08x magic=0x%08x",
            Integer.toUnsignedLong(m.getInt(toAddr(0x2a60L))),
            Integer.toUnsignedLong(m.getInt(toAddr(0x2a64L)))));
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        long[] E={0xbd40L, 0x380cL, 0x3740L, 0x2a44L};  // router, OUT parser, IN responder, flag check
        Set<Function> done=new LinkedHashSet<>();
        try{ for(long e:E){ Function f=currentProgram.getFunctionManager().getFunctionContaining(toAddr(e));
            if(f==null||!done.add(f)) continue;
            println("DECOMPILE "+fn(f));
            DecompileResults r=d.decompileFunction(f,90,monitor);
            if(r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());
        }} finally{d.dispose();}
        println("DONE decompiled="+done.size());
    }
}
