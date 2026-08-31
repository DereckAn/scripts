// Read-only report resolving the bootloader (PID 1b7f) READ-command scheduling
// context: the literal values behind the state/buffer base pointers, every
// function that loads those bases, the transitive call graph above the vendor-HID
// report router / OUT parser / IN responder / service loop, and which interrupt
// vectors reach them. No device access; -readOnly -noanalysis.
// @category Falchion
import java.util.*;
import ghidra.app.decompiler.*; import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address; import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*; import ghidra.program.model.symbol.Reference;

public class FalchionBootloaderReadScheduling extends GhidraScript {
    private String fn(Function f){return f==null?"none":f.getName()+"@"+f.getEntryPoint();}

    private Set<Function> callersOf(Function f){
        Set<Function> s=new LinkedHashSet<>();
        for(Reference r:currentProgram.getReferenceManager().getReferencesTo(f.getEntryPoint())){
            Function c=currentProgram.getFunctionManager().getFunctionContaining(r.getFromAddress());
            if(c!=null&&!c.equals(f))s.add(c);}
        return s;
    }

    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only bootloader READ-scheduling / state-ownership report");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory();
        FunctionManager fm=currentProgram.getFunctionManager();

        // ---- 1. resolve the literal-pool pointer words referenced by the protocol code
        long[] PTR={0x2a60L,0x2a64L,0x2e60L,0x3808L,0x3a68L,0x3a6cL,0x3a70L,0x3a74L,0x3a78L,
                    0x3ab4L,0x3af8L,0x3b60L,0x3b94L,0x3d1cL,0x3fbcL,0x4158L};
        println("=== SECTION 1: literal-pool pointer values ===");
        TreeSet<Long> bases=new TreeSet<>();
        for(long p:PTR){
            long v=Integer.toUnsignedLong(m.getInt(toAddr(p)));
            println(String.format("PTR DAT_%08x = 0x%08x", p, v));
            bases.add(v);
        }

        // ---- 2. every literal-pool word in the image equal to one of those bases,
        //         and the function that loads it
        println("=== SECTION 2: literal-pool occurrences of each base and their loaders ===");
        Map<Long,Set<Function>> loaders=new LinkedHashMap<>();
        for(long b:bases) loaders.put(b,new LinkedHashSet<Function>());
        for(MemoryBlock blk:m.getBlocks()){
            if(!blk.isInitialized()) continue;
            long s=blk.getStart().getOffset(), e=blk.getEnd().getOffset();
            for(long a=(s+3)&~3L; a+3<=e; a+=4){
                long v=Integer.toUnsignedLong(m.getInt(toAddr(a)));
                if(!loaders.containsKey(v)) continue;
                StringBuilder sb=new StringBuilder(String.format("LITERAL 0x%08x = 0x%08x refs=", a, v));
                for(Reference r:currentProgram.getReferenceManager().getReferencesTo(toAddr(a))){
                    Function c=fm.getFunctionContaining(r.getFromAddress());
                    sb.append(String.format(" %s<-%s", r.getFromAddress(), fn(c)));
                    if(c!=null) loaders.get(v).add(c);
                }
                println(sb.toString());
            }
        }
        for(long b:bases){
            StringBuilder sb=new StringBuilder(String.format("BASE 0x%08x loaders=", b));
            for(Function f:loaders.get(b)) sb.append(" ").append(fn(f));
            println(sb.toString());
        }

        // ---- 3. transitive callers of the protocol entry points
        println("=== SECTION 3: transitive callers (call graph upward) ===");
        long[] ROOTS={0xbd40L,0x380cL,0x3740L,0x3a7cL,0x2db8L,0x3b64L,0xaff0L,0x4f7cL,0x7da8L,0x7ec8L};
        for(long r0:ROOTS){
            Function f0=fm.getFunctionContaining(toAddr(r0));
            if(f0==null){println(String.format("ROOT 0x%04x -> no function", r0));continue;}
            println("ROOT "+fn(f0));
            Set<Function> seen=new LinkedHashSet<>(); Deque<Function> q=new ArrayDeque<>();
            q.add(f0); seen.add(f0);
            while(!q.isEmpty()){
                Function cur=q.poll();
                Set<Function> cs=callersOf(cur);
                StringBuilder sb=new StringBuilder("  "+fn(cur)+" <- ");
                if(cs.isEmpty()) sb.append("(no callers: root/vector/indirect)");
                for(Function c:cs){ sb.append(fn(c)).append(" "); if(seen.add(c)) q.add(c); }
                println(sb.toString());
            }
        }

        // ---- 4. exception/interrupt vector table at 0x0 and what each handler is
        println("=== SECTION 4: vector table 0x00000000..0x000000ff ===");
        for(int i=0;i<64;i++){
            long a=i*4L;
            long v=Integer.toUnsignedLong(m.getInt(toAddr(a)));
            if(v==0) continue;
            Function h=fm.getFunctionContaining(toAddr(v&~1L));
            println(String.format("VECTOR[%2d] @0x%08x = 0x%08x %s", i, a, v, fn(h)));
        }

        // ---- 5. dump the framing/dispatch bodies as raw disassembly for the
        //         state-byte accesses, so offsets 0x34..0x39 can be attributed
        println("=== SECTION 5: disassembly of state-byte accesses ===");
        long[][] RANGES={{0x2db8L,0x2e60L},{0x3740L,0x3808L},{0x380cL,0x3a68L},{0x3a7cL,0x3ab8L},{0xbd40L,0xbd80L}};
        for(long[] rg:RANGES){
            println(String.format("--- range 0x%05x..0x%05x ---", rg[0], rg[1]));
            Address a=toAddr(rg[0]);
            Listing l=currentProgram.getListing();
            while(a.getOffset()<rg[1]){
                Instruction ins=l.getInstructionAt(a);
                if(ins==null){ a=a.add(2); continue; }
                println(String.format("%s  %-28s %s", a, ins.toString(), ins.getMnemonicString()));
                a=a.add(ins.getLength());
            }
        }
        println("DONE");
    }
}
