// Read-only companion report: locates the indirect registration of the vendor-HID
// report router FUN_0000bd40, decompiles the reset/main path, the service-loop
// caller, the interrupt handlers present in the vector table, and the wait
// primitive used by the synchronous flash READ. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address; import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*; import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderReadContext extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only report: scheduling context of the vendor-HID router");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory(); FunctionManager fm=currentProgram.getFunctionManager();

        // ---- A. where is 0xbd40/0xbd41 stored as data (callback table / literal)?
        println("=== A: image words equal to a router/handler code pointer ===");
        long[] TARGETS={0xbd40L,0xbd41L,0x380cL,0x380dL,0x3740L,0x3741L,0x3a7cL,0x3a7dL,
                        0x48d1L,0x4b9dL,0x4b0dL,0x4b1dL,0x2e65L};
        Set<Long> tset=new HashSet<>(); for(long t:TARGETS) tset.add(t);
        for(MemoryBlock blk:m.getBlocks()){
            if(!blk.isInitialized()) continue;
            long s=blk.getStart().getOffset(), e=blk.getEnd().getOffset();
            for(long a=(s+3)&~3L; a+3<=e; a+=4){
                long v=Integer.toUnsignedLong(m.getInt(toAddr(a)));
                if(!tset.contains(v)) continue;
                StringBuilder sb=new StringBuilder(String.format("WORD 0x%08x = 0x%08x refs=", a, v));
                for(Reference r:currentProgram.getReferenceManager().getReferencesTo(toAddr(a)))
                    sb.append(String.format(" %s<-%s", r.getFromAddress(), fn(fm.getFunctionContaining(r.getFromAddress()))));
                println(sb.toString());
            }
        }

        // ---- B. decompile the reset/main path, ISR handlers, and wait primitives
        println("=== B: decompilation ===");
        long[] E={0x2d4L,0x148L,0x7ec8L,0x2e90L,0x48d0L,0x4b9cL,0x4b0cL,0x4b1cL,
                  0x7da8L,0x4f7cL,0x4facL,0xaff0L,0x2f0cL,0x5470L};
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        Set<Function> done=new LinkedHashSet<>();
        try{ for(long e:E){
            Function f=fm.getFunctionContaining(toAddr(e));
            if(f==null){println(String.format("NOFUNC 0x%05x",e));continue;}
            if(!done.add(f)) continue;
            Set<String> cs=new LinkedHashSet<>();
            for(Reference r:currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint())){
                Function c=fm.getFunctionContaining(r.getFromAddress());
                if(c!=null&&!c.equals(f))cs.add(fn(c));}
            println("DECOMPILE "+fn(f)+" callers="+cs);
            DecompileResults r=d.decompileFunction(f,120,monitor);
            if(r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());
        }} finally{d.dispose();}

        // ---- C. raw disassembly of undefined vector handlers (no function defined)
        println("=== C: disassembly of vector targets lacking functions ===");
        long[][] RG={{0x48d0L,0x4900L},{0x4b0cL,0x4b40L},{0x4b9cL,0x4bd0L},{0x2e64L,0x2e90L},
                     {0x30aL,0x340L}};
        Listing l=currentProgram.getListing();
        for(long[] rg:RG){
            println(String.format("--- 0x%05x..0x%05x ---",rg[0],rg[1]));
            Address a=toAddr(rg[0]);
            while(a.getOffset()<rg[1]){
                Instruction ins=l.getInstructionAt(a);
                if(ins==null){println(a+"  (no instruction)"); a=a.add(2); continue;}
                println(String.format("%s  %s", a, ins.toString()));
                a=a.add(ins.getLength());
            }
        }
        println("DONE decompiled="+done.size());
    }
}
