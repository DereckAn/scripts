// Read-only report: proves the scheduling context of the vendor-HID report router.
// Disassembles the NVIC vector handlers that Ghidra left undefined, resolves the
// USB driver callback slot written by FUN_0000b0d0 and every reader of that slot,
// and disassembles the 0x1f EXEC erase-gate. Uses PseudoDisassembler so the
// program database is not modified. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler; import ghidra.app.util.PseudoInstruction;
import ghidra.program.model.address.Address; import ghidra.program.model.listing.*;
import ghidra.program.model.mem.Memory; import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderIrqContext extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    private void pdis(String tag,long from,int count){
        println(String.format("--- %s 0x%05x ---",tag,from));
        PseudoDisassembler pd=new PseudoDisassembler(currentProgram);
        Address a=toAddr(from);
        for(int i=0;i<count;i++){
            try{
                Listing l=currentProgram.getListing();
                Instruction ex=l.getInstructionAt(a);
                if(ex!=null){println(String.format("%s  %s",a,ex.toString())); a=a.add(ex.getLength()); continue;}
                PseudoInstruction ins=pd.disassemble(a);
                if(ins==null){println(a+"  (undecodable)"); break;}
                println(String.format("%s  %s",a,ins.toString()));
                a=a.add(ins.getLength());
            }catch(Exception e){println(a+"  (error "+e.getMessage()+")"); break;}
        }
    }
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only proof of the vendor-HID router's scheduling context");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory(); FunctionManager fm=currentProgram.getFunctionManager();

        println("=== J: NVIC vector handlers left undefined by analysis ===");
        pdis("SysTick vector[15] handler",0x48d0L,6);
        pdis("IRQ6 vector[22] handler",0x4b9cL,24);
        pdis("IRQ36 vector[52] handler",0x4b0cL,10);
        pdis("IRQ37 vector[53] handler",0x4b1cL,10);

        println("=== K: USB callback registration (FUN_0000b0d0 family) ===");
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        long[] E={0xb0d0L,0xb104L,0xb124L,0xb0dcL,0xbd90L,0xbd10L,0xbfc8L,0xbf14L,0x7d7cL};
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

        println("=== L: 0x1f EXEC erase-gate (sub-op 0x01) disassembly ===");
        Listing l=currentProgram.getListing(); Address a=toAddr(0x38ceL);
        while(a.getOffset()<0x3950L){
            Instruction ins=l.getInstructionAt(a);
            if(ins==null){println(String.format("%s  .word 0x%08x",a,
                Integer.toUnsignedLong(m.getInt(a)))); a=a.add(4); continue;}
            println(String.format("%s  %s",a,ins.toString())); a=a.add(ins.getLength());
        }
        println("DONE");
    }
}
