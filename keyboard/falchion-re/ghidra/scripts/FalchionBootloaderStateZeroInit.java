// Read-only report: decodes the bootloader's ARM Region$$Table (reached from the
// reset vector via the __scatterload loop at 0x00000148) and reports which entry
// covers the vendor-HID protocol state block at 0x18012a8c -- i.e. whether the
// pending byte state+0x34 and the response buffer state+4 are zero-initialised
// before main() runs. No device access.
// @category Falchion
import java.util.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.Memory;

public class FalchionBootloaderStateZeroInit extends GhidraScript {
    public void run() throws Exception {
        println("PROGRAM "+currentProgram.getName());
        println("PURPOSE offline read-only report: startup zero-init of the protocol state");
        if(!currentProgram.getName().equals("bootloader_primary.bin")){println("need bootloader");return;}
        Memory m=currentProgram.getMemory();
        // reset vector -> 0x000002f4 -> blx DAT_0000033c ; bx DAT_00000340
        println(String.format("RESET vector[1] = 0x%08x",
            Integer.toUnsignedLong(m.getInt(toAddr(4L)))));
        println(String.format("  0x00000302 blx *0x0000033c = 0x%08x   (pre-main init)",
            Integer.toUnsignedLong(m.getInt(toAddr(0x33cL)))));
        println(String.format("  0x00000306 bx  *0x00000340 = 0x%08x   (entry stub 0x140)",
            Integer.toUnsignedLong(m.getInt(toAddr(0x340L)))));
        println("  0x00000140: bl 0x00000148 (__scatterload) ; bl 0x000002d4 (__rt_entry)");
        // __scatterload: adr r0,[0x174]; ldm r0,{r10,r11}; add r10,r0; add r11,r0
        long anchor=0x174L;
        long base=(anchor+Integer.toUnsignedLong(m.getInt(toAddr(anchor))))&0xffffffffL;
        long limit=(anchor+Integer.toUnsignedLong(m.getInt(toAddr(anchor+4))))&0xffffffffL;
        println(String.format("REGION_TABLE base=0x%08x limit=0x%08x entries=%d",
            base, limit, (limit-base)/16));
        long S=0x18012a8cL, T=0x18011a8cL, W=0x18010bd4L;
        for(long a=base;a<limit;a+=16){
            long src=Integer.toUnsignedLong(m.getInt(toAddr(a)));
            long dst=Integer.toUnsignedLong(m.getInt(toAddr(a+4)));
            long len=Integer.toUnsignedLong(m.getInt(toAddr(a+8)));
            long fn =Integer.toUnsignedLong(m.getInt(toAddr(a+12)));
            StringBuilder cov=new StringBuilder();
            for(Object[] o:new Object[][]{{"W",W},{"T",T},{"S",S},{"S+0x34",S+0x34},
                                          {"S+0x36",S+0x36},{"S+0x38",S+0x38},{"S+4",S+4}}){
                long v=((Number)o[1]).longValue();
                if(dst<=v && v<dst+len) cov.append(" ").append(o[0]);
            }
            StringBuilder pro=new StringBuilder();
            for(int i=0;i<12;i++) pro.append(String.format("%02x ", m.getByte(toAddr((fn&~1L)+i))&0xff));
            println(String.format("ENTRY @0x%08x src=0x%08x dst=0x%08x len=0x%x end=0x%08x fn=0x%08x",
                a,src,dst,len,dst+len,fn));
            println("   handler bytes: "+pro.toString().trim());
            println("   covers:"+(cov.length()==0?" -":cov.toString()));
        }
        println("DONE");
    }
}
