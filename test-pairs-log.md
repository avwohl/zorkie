# ZIL to .z Compilation Test Log

## Previously Tested Pairs (Failed - source didn't match binary)
1. Planetfall ZIL vs Planetfall .z3 - source mismatch
2. (need to fill in from previous attempts)

## Current Test Candidates

### From zifmia repository (github.com/jeffnyman/zifmia)
- ✅ zil_test.zil → zil_test.z3 (v3)
- ✅ cloak.zil → cloak.z3 (v3)
- ✅ cloak_plus.zil → cloak_plus.z5 (v5)
- ✅ advent.zil + hints.zil → advent.z3 (v3, Colossal Cave Adventure)

These are explicitly compiled with ZILF by Jesse McGrew, so they should be a good match.

## Test Results

### Test 1: zil_test.zil from zifmia
**Status:** ❌ Incompatible
**Reason:** Uses ZILF-specific syntax (backtick ` character at line 105) that our compiler doesn't support yet
**Conclusion:** This file was compiled with ZILF and uses ZILF-specific features, so comparison wouldn't be meaningful

### Test 2: cloak.zil from zifmia
**Status:** Pending - will likely have same ZILF compatibility issues

### Test 3: Zork1 (Infocom source vs Infocom binary)
**Status:** ❌ Our compiler incomplete
**Source:** `/home/wohl/zorkie/test-games/zork1/zork1.zil`
**Official binary:** `/home/wohl/zorkie/test-games/zork1/COMPILED/zork1.z3` (Release 119, Serial 880429, 86,838 bytes)
**Our output:** `zork1-ours.z3` (622 bytes)
**Conclusion:** Our compiler only generates a minimal stub file. The compiler is not yet complete enough to generate full game binaries.

## Analysis

### Finding #1: ZILF vs Infocom ZIL
The .z files from zifmia were explicitly compiled with ZILF (modern compiler by Jesse McGrew), not the original Infocom compiler. ZILF has syntax extensions like:
- Backtick (`) operator (encountered at line 105 of parser.zil)
- Other modern conveniences

These make it incompatible for testing our Infocom-style compiler.

### Finding #2: Our Compiler Status
Testing against authentic Infocom source (Zork1) revealed our compiler generates only 622 bytes vs the original 86,838 bytes. Our compiler is still in development and missing:
- Complete code generation
- Full object table generation
- Dictionary generation
- String encoding
- Many other components

### Conclusion
**We cannot yet perform meaningful binary comparison tests because:**
1. ZILF-compiled sources use incompatible syntax extensions
2. Our compiler doesn't generate complete binaries yet

**Next steps should be:**
1. Complete the compiler implementation first
2. Then test against Infocom ZIL source + Infocom binaries (like Zork1)
3. Only compare against ZILF output after implementing ZILF syntax extensions
