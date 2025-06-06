#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WARNING! Here lay dragons!

This is a *very* rudimentary script that attempts to scrape the IBM documentation website
to generate lib/asm-docs/generated/asm-docs-power.ts.

It is a maddeningly difficult task to do this, for the following reasons:

1. The IBM documentation site is rendered dynamically using React.
   It requires the use of Selenium to read the rendered pages.
2. There's no easy way to scrape the documentation API that provides each page.
   It's protected by a cookie generated by visiting the documentation website for the first time.
3. While it's possible to scrape the user-visible pages for documentation,
   it's incredibly hard because of the following reasons:

   a. Some pages have invisible elements in the headers that make matching elements very difficult.
   b. Some pages are missing entire sections of content that are necessary to generate true documentation.
   c. Some pages are written without an introduction paragraph for the instruction mnemonic, making the
      resulting documentation impossible to understand.
   d. Some pages, specifically for instructions that take no arguments, are missing the table that lists the
      mnemonics in order.
   e. Some pages have a completely broken layout, requiring manual editing of the resulting documentation for
      it to be understandable.

For more details, see here: https://github.com/compiler-explorer/compiler-explorer/pull/6665

If anyone is braver than me, feel free to try and pick up this work, and increment
the counter below.

hours_of_life_wasted = 10.2
"""

import argparse
import re
import json
from time import sleep
from bs4 import BeautifulSoup, NavigableString, Tag
from tqdm import tqdm
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import os

# Unfortunately, we have to use Selenium because IBM made their documentation dynamic.
from selenium import webdriver
from selenium.webdriver.common.by import By

parser = argparse.ArgumentParser(description="Docenizes the HTML version of the official IBM POWER Assembler Language Reference")
parser.add_argument('-o', '--outputpath', type=str,
                    help='Final path of the .ts file. Default is ./asm-docs-power.ts',
                    default='./asm-docs-power.ts')

# Explanation of how this link list works:
# 1. Go to the IBM reference docs for AIX at https://www.ibm.com/docs/en/aix/7.3?topic=reference-assembler-overview
# 2. Get the links for each instruction with:
#    ```javascript
#    var links = [];
#    document.querySelectorAll("a.ibmdocs-toc-link").forEach((item) => {
#        if (item.href && item.href.endsWith("instruction"))
#            links.push(item.href);
#    });
#    ```
# 3. Put the output into this list.

links = [
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-abs-absolute-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-add-add-cax-compute-address-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-addc-add-carrying-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-adde-ae-add-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-addi-add-immediate-cal-compute-address-lower-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-addic-ai-add-immediate-carrying-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-addic-ai-add-immediate-carrying-record-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-addis-cau-add-immediate-shifted-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-addme-ame-add-minus-one-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-addze-aze-add-zero-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-andc-complement-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-andi-andil-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-andis-andiu-immediate-shifted-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-b-branch-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-bc-branch-conditional-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-bcctr-bcc-branch-conditional-count-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-bclr-bcr-branch-conditional-link-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-clcs-cache-line-compute-size-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-clf-cache-line-flush-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cli-cache-line-invalidate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cmp-compare-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cmpi-compare-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cmpl-compare-logical-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cmpli-compare-logical-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cntlzd-count-leading-zeros-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cntlzw-cntlz-count-leading-zeros-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-crand-condition-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-crandc-condition-register-complement-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-creqv-condition-register-equivalent-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-crnand-condition-register-nand-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-crnor-condition-register-nor-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-cror-condition-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-crorc-condition-register-complement-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-crxor-condition-register-xor-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dcbf-data-cache-block-flush-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dcbi-data-cache-block-invalidate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dcbst-data-cache-block-store-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dcbt-data-cache-block-touch-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dcbtst-data-cache-block-touch-store-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-dcbz-dclz-data-cache-block-set-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dclst-data-cache-line-store-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-div-divide-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-divd-divide-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-divdu-divide-double-word-unsigned-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-divs-divide-short-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-divw-divide-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-divwu-divide-word-unsigned-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-doz-difference-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-dozi-difference-zero-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-eciwx-external-control-in-word-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ecowx-external-control-out-word-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-eieio-enforce-in-order-execution-io-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-extsw-extend-sign-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-eqv-equivalent-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-extsb-extend-sign-byte-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-extsh-exts-extend-sign-halfword-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fabs-floating-absolute-value-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fadd-fa-floating-add-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-fcfid-floating-convert-from-integer-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fcmpo-floating-compare-ordered-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fcmpu-floating-compare-unordered-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fctid-floating-convert-integer-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-fctidz-floating-convert-integer-double-word-round-toward-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fctiw-fcir-floating-convert-integer-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-fctiwz-fcirz-floating-convert-integer-word-round-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fdiv-fd-floating-divide-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fmadd-fma-floating-multiply-add-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fmr-floating-move-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fmsub-fms-floating-multiply-subtract-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fmul-fm-floating-multiply-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fnabs-floating-negative-absolute-value-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fneg-floating-negate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fnmadd-fnma-floating-negative-multiply-add-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fnmsub-fnms-floating-negative-multiply-subtract-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fres-floating-reciprocal-estimate-single-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-frsp-floating-round-single-precision-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-frsqrte-floating-reciprocal-square-root-estimate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fsel-floating-point-select-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fsqrt-floating-square-root-double-precision-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fsqrts-floating-square-root-single-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-fsub-fs-floating-subtract-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-icbi-instruction-cache-block-invalidate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-isync-ics-instruction-synchronize-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lbz-load-byte-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lbzu-load-byte-zero-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lbzux-load-byte-zero-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lbzx-load-byte-zero-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ld-load-doubleword-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ldarx-load-doubleword-reserve-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ldu-load-doubleword-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ldux-load-doubleword-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ldx-load-doubleword-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfd-load-floating-point-double-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfdu-load-floating-point-double-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-lfdux-load-floating-point-double-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfdx-load-floating-point-double-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfq-load-floating-point-quad-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfqu-load-floating-point-quad-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-lfqux-load-floating-point-quad-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfqx-load-floating-point-quad-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfs-load-floating-point-single-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfsu-load-floating-point-single-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-lfsux-load-floating-point-single-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lfsx-load-floating-point-single-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lha-load-half-algebraic-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhau-load-half-algebraic-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhaux-load-half-algebraic-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhax-load-half-algebraic-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhbrx-load-half-byte-reverse-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhz-load-half-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhzu-load-half-zero-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhzux-load-half-zero-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lhzx-load-half-zero-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lmw-lm-load-multiple-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lq-load-quad-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lscbx-load-string-compare-byte-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lswi-lsi-load-string-word-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lswx-lsx-load-string-word-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwa-load-word-algebraic-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwarx-load-word-reserve-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwaux-load-word-algebraic-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwax-load-word-algebraic-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-lwbrx-lbrx-load-word-byte-reverse-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwz-l-load-word-zero-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwzu-lu-load-word-zero-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-lwzux-lux-load-word-zero-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-lwzx-lx-load-word-zero-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-maskg-mask-generate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-maskir-mask-insert-from-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mcrf-move-condition-register-field-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mcrfs-move-condition-register-from-fpscr-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mcrxr-move-condition-register-from-xer-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mfcr-move-from-condition-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mffs-move-from-fpscr-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mfmsr-move-from-machine-state-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-mfocrf-move-from-one-condition-register-field-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mfspr-move-from-special-purpose-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mfsr-move-from-segment-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mfsri-move-from-segment-register-indirect-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mfsrin-move-from-segment-register-indirect-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtcrf-move-condition-register-fields-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtfsb0-move-fpscr-bit-0-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtfsb1-move-fpscr-bit-1-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtfsf-move-fpscr-fields-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtfsfi-move-fpscr-field-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtocrf-move-one-condition-register-field-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mtspr-move-special-purpose-register-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mul-multiply-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mulhd-multiply-high-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mulhdu-multiply-high-double-word-unsigned-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mulhw-multiply-high-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mulhwu-multiply-high-word-unsigned-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mulld-multiply-low-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mulli-muli-multiply-low-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-mullw-muls-multiply-low-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-nabs-negative-absolute-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-nand-nand-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-neg-negate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-nor-nor-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-orc-complement-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-ori-oril-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-oris-oriu-immediate-shifted-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-popcntbd-population-count-byte-doubleword-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-rac-real-address-compute-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-rfi-return-from-interrupt-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-rfid-return-from-interrupt-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-rfsvc-return-from-svc-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rldcl-rotate-left-double-word-then-clear-left-instruction",
    # Two pages document rldicl. The one suffixed `-1` is clearer.
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rldicl-rotate-left-double-word-immediate-then-clear-left-instruction-1",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rldcr-rotate-left-double-word-then-clear-right-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rldic-rotate-left-double-word-immediate-then-clear-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rldicr-rotate-left-double-word-immediate-then-clear-right-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rldimi-rotate-left-double-word-immediate-then-mask-insert-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-rlmi-rotate-left-then-mask-insert-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rlwimi-rlimi-rotate-left-word-immediate-then-mask-insert-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rlwinm-rlinm-rotate-left-word-immediate-then-mask-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-rlwnm-rlnm-rotate-left-word-then-mask-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-rrib-rotate-right-insert-bit-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sc-system-call-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-scv-system-call-vectored-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-si-subtract-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-si-subtract-immediate-record-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sld-shift-left-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sle-shift-left-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sleq-shift-left-extended-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sliq-shift-left-immediate-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-slliq-shift-left-long-immediate-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sllq-shift-left-long-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-slq-shift-left-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-slw-sl-shift-left-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srad-shift-right-algebraic-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-sradi-shift-right-algebraic-double-word-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sraiq-shift-right-algebraic-immediate-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sraq-shift-right-algebraic-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sraw-sra-shift-right-algebraic-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-srawi-srai-shift-right-algebraic-word-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srd-shift-right-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sre-shift-right-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srea-shift-right-extended-algebraic-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sreq-shift-right-extended-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sriq-shift-right-immediate-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srliq-shift-right-long-immediate-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srlq-shift-right-long-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srq-shift-right-mq-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-srw-sr-shift-right-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stb-store-byte-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stbu-store-byte-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stbux-store-byte-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stbx-store-byte-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-std-store-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stdcx-store-double-word-conditional-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stdu-store-double-word-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stdux-store-double-word-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stdx-store-double-word-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfd-store-floating-point-double-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfdu-store-floating-point-double-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-stfdux-store-floating-point-double-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfdx-store-floating-point-double-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfq-store-floating-point-quad-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfqu-store-floating-point-quad-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-stfqux-store-floating-point-quad-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfqx-store-floating-point-quad-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfs-store-floating-point-single-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfsu-store-floating-point-single-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-stfsux-store-floating-point-single-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stfsx-store-floating-point-single-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sth-store-half-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sthbrx-store-half-byte-reverse-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sthu-store-half-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sthux-store-half-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sthx-store-half-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stmw-stm-store-multiple-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stq-store-quad-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stswi-stsi-store-string-word-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stswx-stsx-store-string-word-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stw-st-store-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-stwbrx-stbrx-store-word-byte-reverse-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stwcx-store-word-conditional-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stwu-stu-store-word-update-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stwux-stux-store-word-update-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-stwx-stx-store-word-indexed-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-subf-subtract-from-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-subfc-sf-subtract-from-carrying-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-subfe-sfe-subtract-from-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-subfic-sfi-subtract-from-immediate-carrying-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-subfme-sfme-subtract-from-minus-one-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-subfze-sfze-subtract-from-zero-extended-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-svc-supervisor-call-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-sync-synchronize-dcs-data-cache-synchronize-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-td-trap-double-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-tdi-trap-double-word-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=is-tlbie-tlbi-translation-look-aside-buffer-invalidate-entry-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-tlbld-load-data-tlb-entry-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-tlbli-load-instruction-tlb-entry-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-tlbsync-translation-look-aside-buffer-synchronize-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-tw-t-trap-word-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-twi-ti-trap-word-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-xor-xor-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-xori-xoril-xor-immediate-instruction",
    "https://www.ibm.com/docs/en/aix/7.3?topic=set-xoris-xoriu-xor-immediate-shift-instruction"
]


def _cleanup(soup: BeautifulSoup) -> Tag | NavigableString | None:
    for tag_name in ["iframe", "table", "link", "script", "meta", "svg", "style", "img", "c4d-masthead-composite", "c4d-masthead", "c4d-skip-to-content", "c4d-masthead-logo", "c4d-top-nav-name", "c4d-top-nav", "c4d-top-name-item", "c4d-megamenu-top-nav-menu", "c4d-search-with-typeahead", "c4d-masthead-global-bar", "c4d-masthead-profile", "c4d-masthead-profile-item", "c4d-megamenu-overlay", "c4d-back-to-top", "c4d-footer-container", "c4d-footer", "c4d-footer-logo", "c4d-language-selector-desktop", "cds-combo-box-item", "c4d-legal-nav", "c4d-footer-logo", "c4d-legal-nav-item", "c4d-legal-nav-cookie-preferences-placeholder", "c4d-language-selector-desktop", "aside"]:
        for tag in soup.find_all(tag_name):
            tag.clear()
            tag.decompose()
    for class_name in ["docs--copy-btn", "tablenoborder", "p"]:
        for tag in soup.find_all("div", { "class": class_name }):
            tag.clear()
            tag.decompose()

    return soup.find_all("div", { "class": "conbody" })


def precache():
    if not os.path.exists("power/.complete-precache"):
        driver = webdriver.Chrome()

        for link in tqdm(links):
            driver.get(link)
            # Wait for the IBM website to render
            sleep(7)
            full_html = driver.find_element(By.CSS_SELECTOR, "html").get_attribute("outerHTML")

            parsed_url = urlparse(link)
            topic = parse_qs(parsed_url.query)['topic'][0]
            with open(f"power/{topic}.html", "w") as fp:
                fp.write(full_html)

        driver.close()

        # Marker file that tells the program that the fetch is complete
        with open("power/.complete-precache", "w") as fp:
            fp.write("true")


def preprocess():
    if not os.path.exists("power/.complete-precache"):
        precache()

    path = Path("power")

    for page in path.glob("*.html"):
        with page.absolute().open("r") as fp:
            soup = BeautifulSoup(fp.read(), "html.parser")
            clean_soup = _cleanup(soup)
            for tag in clean_soup:
                print(tag)

    # with open("power/.complete-preprocess", "w"):
    #   fp.write("true")


def docenizer():
    args = parser.parse_args()
    print("Called with: {}".format(args))
    if not os.path.exists("power/.complete-preprocess"):
        preprocess()

    r"""
    # Extract instruction name from parentheses in title
    tooltip = str(re.findall(r'\(.*?\)', driver.title)).replace("(", "").replace(")", "")

    # Extract body
    body = driver.find_element(By.CSS_SELECTOR, "div.body.conbody")

    # Get mnemonics
    table_rows = driver.find_elements(By.CSS_SELECTOR, "td > strong")
    mnemonics = list({str(it.get_attribute("innerHTML")).upper() for it in table_rows if not bool(re.match(r'.*[A-Z,]\.*', str(it.get_attribute("innerHTML"))))})

    # Body details
    items = body.find_elements(By.XPATH, ".//*")
    outer_html = [it.get_attribute("outerHTML") for it in items]
    try:
        description_index = outer_html.index("<p><strong>Description</strong></p>") + 1
    except ValueError:
        description_index = outer_html.index("<p><strong><strong></strong>Description</strong></p>") + 1
    try:
        parameters_index = outer_html.index("<p><strong>Parameters</strong></p>") - 1
    except ValueError:
        parameters_index = outer_html.index("<p><strong>Examples</strong></p>") - 1

    # Get all description content
    description_raw = outer_html[description_index:parameters_index]
    description_transformed = [
        str(_cleanup(BeautifulSoup(str(it), "html.parser"))) for it in description_raw
    ]
    description_transformed = [it for it in description_transformed if it != ""]
    description = "\n".join([it.replace("\n", " ") for it in description_transformed])

    # If mnemonics is empty, use first item in title
    if len(mnemonics) == 0:
        mnemonics = [driver.title.split("(")[0]]
        if " or " in mnemonics[0]:
            mnemonics = [mnemonics[0].split(" or ")]
        mnemonics = [str(it).upper() for it in mnemonics]

    complete = {
        "url": link,
        "tooltip": tooltip,
        "mnemonics": mnemonics,
        "html": description
    }
    instructions.append(complete)
    with open("power.json", "w") as fp:
        json.dump(instructions, fp)
    """

if __name__ == "__main__":
    docenizer()
