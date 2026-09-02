// Read-only: how Candidate A hands control to Candidate B (RAM 0x18000000) after scatter-load.
// @category Falchion
import java.util.LinkedHashSet; import java.util.Set;
import ghidra.app.decompiler.DecompInterface; import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript; import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function; import ghidra.program.model.symbol.Reference;
public class FalchionCandidateAHandoff extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}
    private Set<String> callers(Function f){Set<String> s=new LinkedHashSet<>();
        for(Reference r:currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint())){
            Function c=currentProgram.getFunctionManager().getFunctionContaining(r.getFromAddress());
            if(c!=null&&!c.equals(f))s.add(fn(c));} return s;}
    private void dec(Function f,DecompInterface d,Set<Function> done){
        if(f==null||!done.add(f))return;
        println("DECOMPILE "+fn(f)+" body="+f.getBody()+" callers="+callers(f));
        DecompileResults r=d.decompileFunction(f,120,monitor);
        println("  completed="+r.decompileCompleted()+" error="+r.getErrorMessage());
        if(r.getDecompiledFunction()!=null)println(r.getDecompiledFunction().getC());
    }
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        if(!currentProgram.getName().equals("app_candidate_a.bin")){println("need app_candidate_a.bin");return;}
        Set<Function> targets=new LinkedHashSet<>();
        // literal 0x18000000 is at file-relative 0x557c in candidate A
        Address lit=toAddr(0x557cL);
        println(String.format("LIT_18000000 @%s = 0x%08x",lit,
            Integer.toUnsignedLong(currentProgram.getMemory().getInt(lit))));
        for(Reference r:currentProgram.getReferenceManager().getReferencesTo(lit)){
            Function f=currentProgram.getFunctionManager().getFunctionContaining(r.getFromAddress());
            println("  ref from="+r.getFromAddress()+" type="+r.getReferenceType()+" fn="+fn(f));
            if(f!=null)targets.add(f);
        }
        // the C-runtime handoff after scatter-load: 0x144 does bl 0x2c8
        for(long e:new long[]{0x2c8L,0x140L}){
            Function f=currentProgram.getFunctionManager().getFunctionContaining(toAddr(e));
            if(f!=null)targets.add(f);
        }
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        Set<Function> done=new LinkedHashSet<>();
        try{ for(Function f:targets) dec(f,d,done);} finally{d.dispose();}
        println("DONE decompiled="+done.size());
    }
}
