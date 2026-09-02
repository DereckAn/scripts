// Read-only report of the bootloader (PID 1b7f) vendor-HID write protocol:
// the OUT-report command dispatcher, the erase/read/program handlers with their
// address guards, and the flash-controller primitives. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function; import ghidra.program.model.symbol.Reference;
public class FalchionBootloaderProtocol extends GhidraScript {
    // service loop -> OUT-report dispatcher -> {erase,read,program} handlers -> primitives
    private static final long[] E = {
        0x3a7cL,  // service loop
        0x2db8L,  // OUT-report command dispatcher (cmd byte @ report+0x34)
        0x3ab8L,  // cmd 0x01 ERASE handler (guard 0x10000<=addr<0x7c000)
        0x3b64L,  // cmd 0x05 READ handler
        0x3afcL,  // cmd 0x51 PROGRAM handler (guard 0x10000<=addr<0x7c000)
        0x3ca8L,  // erase primitive (controller cmd 8/9/10)
        0x40a4L,  // program primitive (transfer descriptor, dir=0)
        0x3f08L,  // read primitive (transfer descriptor, dir=1)
        0x2f0cL,  // flash transfer engine
    };
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    private Set<String> callers(Function f){Set<String> s=new LinkedHashSet<>();
        for(Reference r:currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint())){
            Function c=currentProgram.getFunctionManager().getFunctionContaining(r.getFromAddress());
            if(c!=null&&!c.equals(f))s.add(fn(c));} return s;}
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only bootloader vendor-HID write-protocol report");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        Set<Function> done=new LinkedHashSet<>();
        try{ for(long e:E){ Function f=currentProgram.getFunctionManager().getFunctionContaining(toAddr(e));
            if(f==null||!done.add(f)) continue;
            println("DECOMPILE "+fn(f)+" callers="+callers(f));
            DecompileResults r=d.decompileFunction(f,90,monitor);
            if(r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());
        }} finally{d.dispose();}
        println("DONE decompiled="+done.size());
    }
}
