// Read-only report: the SysTick reload/period constants, the service-loop flag
// pair ownership, the vendor-HID callback registration table, and instruction-level
// disassembly of the 0x1f EXEC parser gates (pending byte, lock bit) and of the
// 0x0f/0x2a responders. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address; import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*; import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderTickProof extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    private void dis(long from,long to) throws Exception {
        println(String.format("--- 0x%05x..0x%05x ---",from,to));
        Listing l=currentProgram.getListing(); Address a=toAddr(from);
        while(a.getOffset()<to){
            Instruction ins=l.getInstructionAt(a);
            if(ins==null){
                println(String.format("%s  .word 0x%08x",a,
                    Integer.toUnsignedLong(currentProgram.getMemory().getInt(a))));
                a=a.add(4); continue;
            }
            println(String.format("%s  %s",a,ins.toString()));
            a=a.add(ins.getLength());
        }
    }
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only SysTick / gate-ordering proof report");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory(); FunctionManager fm=currentProgram.getFunctionManager();

        println("=== D: constants ===");
        long[] C={0x7f90L,0x7f94L,0x7f98L,0x7f9cL,0x7fa0L,0x7fa4L,0x2eacL,0x7db0L,0x4fa8L,
                  0x48d8L,0x490cL,0xb0ccL};
        for(long c:C) println(String.format("WORD DAT_%08x = 0x%08x", c,
            Integer.toUnsignedLong(m.getInt(toAddr(c)))));

        println("=== E: callback table around 0x7e00 ===");
        for(long a=0x7de0L;a<0x7e40L;a+=4){
            StringBuilder sb=new StringBuilder(String.format("0x%08x = 0x%08x", a,
                Integer.toUnsignedLong(m.getInt(toAddr(a)))));
            for(Reference r:currentProgram.getReferenceManager().getReferencesTo(toAddr(a)))
                sb.append(String.format("  ref<-%s %s", r.getFromAddress(),
                    fn(fm.getFunctionContaining(r.getFromAddress()))));
            println(sb.toString());
        }

        println("=== F: decompile registration + response senders ===");
        long[] E={0x7db4L,0xaec8L,0xaea0L,0xa5b0L,0x26d0L,0x36fcL,0x30b0L};
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        Set<Function> done=new LinkedHashSet<>();
        try{ for(long e:E){
            Function f=fm.getFunctionContaining(toAddr(e));
            if(f==null){println(String.format("NOFUNC 0x%05x",e));continue;}
            if(!done.add(f))continue;
            Set<String> cs=new LinkedHashSet<>();
            for(Reference r:currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint())){
                Function c=fm.getFunctionContaining(r.getFromAddress());
                if(c!=null&&!c.equals(f))cs.add(fn(c));}
            println("DECOMPILE "+fn(f)+" callers="+cs);
            DecompileResults r=d.decompileFunction(f,120,monitor);
            if(r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());
        }} finally{d.dispose();}

        println("=== G: SysTick handler / service loop / dispatcher disassembly ===");
        dis(0x48d0L,0x48dcL);          // SysTick_Handler
        dis(0x3a7cL,0x3ab8L);          // service loop
        dis(0x2db8L,0x2e64L);          // FUN_00002db8 dispatcher
        println("=== H: 0x1f EXEC parser gates (pending byte / lock bit) ===");
        dis(0x3950L,0x3a08L);          // sub-op 1 / 5 / 0x51 gate region
        println("=== I: 0x0f + 0x2a responders ===");
        dis(0x37a8L,0x3808L);
        println("DONE");
    }
}
