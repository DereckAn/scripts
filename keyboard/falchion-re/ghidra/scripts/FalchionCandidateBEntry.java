// Read-only: characterize Candidate B's runtime entry at RAM 0x1800023a.
// @category Falchion
import java.util.LinkedHashSet; import java.util.Set;
import ghidra.app.decompiler.DecompInterface; import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript; import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function; import ghidra.program.model.symbol.Reference;
public class FalchionCandidateBEntry extends GhidraScript {
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
        if(!currentProgram.getName().equals("app_candidate_b_18000000.bin")){println("need rebased B");return;}
        Address entry=toAddr(0x1800023aL);
        Function ef=currentProgram.getFunctionManager().getFunctionContaining(entry);
        if(ef==null){ disassemble(entry); createFunction(entry,"CandidateB_Entry");
            ef=currentProgram.getFunctionManager().getFunctionContaining(entry);}
        println("ENTRY 0x1800023a fn="+fn(ef));
        // who references 0x1800023a? (the loader veneer target)
        println("REFS_TO 0x1800023a:");
        for(Reference r:currentProgram.getReferenceManager().getReferencesTo(entry))
            println("  from="+r.getFromAddress()+" type="+r.getReferenceType());
        // is the known dispatcher 0x18001fbe a function?
        Function disp=currentProgram.getFunctionManager().getFunctionContaining(toAddr(0x18001fbeL));
        println("KNOWN_DISPATCHER 0x18001fbe fn="+fn(disp));
        DecompInterface d=new DecompInterface(); d.openProgram(currentProgram);
        Set<Function> done=new LinkedHashSet<>();
        try{ dec(ef,d,done); } finally{d.dispose();}
        println("DONE");
    }
}
