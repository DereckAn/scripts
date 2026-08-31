// Read-only report: locates the endpoint-completion handler pointers
// (FUN_0000744c / FUN_00007554 / FUN_000076ac) inside the USB driver's endpoint
// table and reports every function that references that table, closing the chain
// from the NVIC USB interrupt to the vendor-HID router. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*; import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.Reference; import ghidra.program.model.address.Address;

public class FalchionBootloaderEpTable extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only report: USB endpoint handler table -> router chain");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory(); FunctionManager fm=currentProgram.getFunctionManager();
        Set<Long> T=new HashSet<>(Arrays.asList(0x744dL,0x7555L,0x76adL,0x7605L,0x7659L,0x7501L,0x73f9L,
                                                0x4b9dL,0xaa2cL,0xaa2dL));
        println("=== P: image words equal to an endpoint-handler pointer ===");
        for(MemoryBlock blk:m.getBlocks()){
            if(!blk.isInitialized())continue;
            long s=blk.getStart().getOffset(), e=blk.getEnd().getOffset();
            for(long a=(s+3)&~3L;a+3<=e;a+=4){
                long v=Integer.toUnsignedLong(m.getInt(toAddr(a)));
                if(!T.contains(v))continue;
                StringBuilder sb=new StringBuilder(String.format("WORD 0x%08x = 0x%08x refs=",a,v));
                for(Reference r:currentProgram.getReferenceManager().getReferencesTo(toAddr(a)))
                    sb.append(String.format(" %s<-%s",r.getFromAddress(),
                        fn(fm.getFunctionContaining(r.getFromAddress()))));
                println(sb.toString());
            }
        }
        println("=== Q: bytes 0x4b9c..0x4d34 (USB IRQ handler body) as raw words ===");
        for(long a=0x4b9cL;a<0x4d3cL;a+=16){
            StringBuilder sb=new StringBuilder(String.format("0x%08x ",a));
            for(int i=0;i<4;i++) sb.append(String.format(" %08x",
                Integer.toUnsignedLong(m.getInt(toAddr(a+i*4)))));
            println(sb.toString());
        }
        println("DONE");
    }
}
