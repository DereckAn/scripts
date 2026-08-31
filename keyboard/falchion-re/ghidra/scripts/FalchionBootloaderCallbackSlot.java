// Read-only report: resolves the USB-driver callback slot written by FUN_0000b0d0
// (which receives the vendor-HID router 0x0000bd41), finds every function that
// loads that slot address, and decompiles them so the router's invocation context
// (interrupt vs. main loop) can be attributed. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address; import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*; import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderCallbackSlot extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only report: USB callback slot ownership");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory(); FunctionManager fm=currentProgram.getFunctionManager();
        long[] SLOTPTR={0xb0d8L,0xb10cL,0xb12cL,0xb0ccL,0xafe8L,0xa5bcL};
        TreeSet<Long> slots=new TreeSet<>();
        println("=== M: slot pointer values ===");
        for(long p:SLOTPTR){ long v=Integer.toUnsignedLong(m.getInt(toAddr(p)));
            println(String.format("PTR DAT_%08x = 0x%08x",p,v)); slots.add(v); }
        println("=== N: literal-pool references to those slots ===");
        Map<Long,Set<Function>> users=new LinkedHashMap<>();
        for(long s:slots) users.put(s,new LinkedHashSet<Function>());
        for(MemoryBlock blk:m.getBlocks()){
            if(!blk.isInitialized())continue;
            long s=blk.getStart().getOffset(), e=blk.getEnd().getOffset();
            for(long a=(s+3)&~3L;a+3<=e;a+=4){
                long v=Integer.toUnsignedLong(m.getInt(toAddr(a)));
                if(!users.containsKey(v))continue;
                StringBuilder sb=new StringBuilder(String.format("LITERAL 0x%08x = 0x%08x refs=",a,v));
                for(Reference r:currentProgram.getReferenceManager().getReferencesTo(toAddr(a))){
                    Function c=fm.getFunctionContaining(r.getFromAddress());
                    sb.append(String.format(" %s<-%s",r.getFromAddress(),fn(c)));
                    if(c!=null)users.get(v).add(c);}
                println(sb.toString());
            }
        }
        println("=== O: decompilation of every function using the router slot ===");
        long routerSlot=Integer.toUnsignedLong(m.getInt(toAddr(0xb0d8L)));
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        Set<Function> done=new LinkedHashSet<>();
        try{ for(Function f:users.get(routerSlot)){
            if(!done.add(f))continue;
            Set<String> cs=new LinkedHashSet<>();
            for(Reference r:currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint())){
                Function c=fm.getFunctionContaining(r.getFromAddress());
                if(c!=null&&!c.equals(f))cs.add(fn(c));}
            println("DECOMPILE "+fn(f)+" callers="+cs);
            DecompileResults r=d.decompileFunction(f,120,monitor);
            if(r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());
        }} finally{d.dispose();}
        println("DONE");
    }
}
