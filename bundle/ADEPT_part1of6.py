#!/usr/bin/env python3
# ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。

為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。

    python ADEPT_part1of6.py              # 解到 .\\ADEPT\\
    python ADEPT_part1of6.py --dest D:\\tools
    python ADEPT_part1of6.py --list       # 只看裡面有什麼，不寫任何檔案

每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
講出來，不會讓你拿到一份安靜壞掉的程式碼。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
PART, N_PARTS = 1, 6   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
TOTAL = 178                       # 整個 repo 有幾個檔案，不是這一批有幾個


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式："blob <長度>\\0" + 內容。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def entries(lines):
    """走過資料區，一個一個吐出 (sha, 路徑, 內容位元組)。"""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#F "):
            i += 1
            continue
        _, sha, count, path = line.split(" ", 3)
        n = int(count)
        # 資料區每一行前面有一個 '#'（那樣整個檔案才仍然是合法的 Python）。
        body = [ln[1:] if ln[:1] == "#" else ln for ln in lines[i + 1:i + 1 + n]]
        yield sha, path, "\n".join(body).encode("utf-8")
        i += 1 + n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unpack the ADEPT text bundle.")
    ap.add_argument("--dest", default="ADEPT", help="解到哪個資料夾（預設 .\\ADEPT）")
    ap.add_argument("--list", action="store_true", help="只列出內容，不寫檔")
    a = ap.parse_args(argv)

    # 用文字模式讀自己：Python 會把 CRLF 讀成 LF，所以這個檔案就算在傳輸途中
    # 被換過行尾也解得開（格式用「行數」而不是「位元組數」正是為了這件事）。
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        start = lines.index(SENTINEL) + 1
    except ValueError:
        print("✗ 找不到資料區 —— 這個檔案被截斷了，或不是完整的 bundle。")
        return 2

    items = list(entries(lines[start:]))
    if not items:
        print("✗ 資料區是空的 —— 這個檔案被截斷了。")
        return 2
    print("這個包裡有 %d 個檔案。" % len(items))
    if a.list:
        for _sha, path, data in items:
            print("  %8d  %s" % (len(data), path))
        return 0

    dest = os.path.abspath(a.dest)
    print("解到  : %s" % dest)
    bad, done = [], 0
    for sha, path, data in items:
        if blob_sha(data) != sha:
            bad.append(path)
            continue
        full = os.path.join(dest, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        tmp = full + ".tmp"                      # atomic：半個檔案不要留在磁碟上
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        done += 1

    if bad:
        print("")
        print("✗ %d 個檔案的內容跟它自己的 SHA 對不上：" % len(bad))
        for path in bad[:12]:
            print("    %s" % path)
        print("")
        print("  這個檔案在傳輸途中被動過（編輯器另存、郵件過濾器改寫都會這樣）。")
        print("  請重新取得一份，不要用編輯器打開後另存。這份程式碼不完整，不要用。")
        return 1

    print("✓ %d 個檔案都解開了，SHA 全部對得上。" % done)

    # 分批的時候要講「還缺幾個」—— 不然使用者不知道自己貼完了沒有。
    # 判斷依據是 tools/FILELIST.txt（它固定在第一批），而不是這一批的數量。
    listing = os.path.join(dest, "tools", "FILELIST.txt")
    have_listing = os.path.isfile(listing)
    missing = []
    if have_listing:
        with open(listing, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rel = line.split(" ", 1)[1]
                    if not os.path.isfile(os.path.join(dest,
                                                       rel.replace("/", os.sep))):
                        missing.append(rel)

    if N_PARTS > 1 and not have_listing:
        # 還沒拿到檔案清單，所以「缺幾個」算不出來。**這時候絕對不能印
        # 「下一步：跑 doctor」** —— 那看起來就像整包已經到位了。
        print("")
        print("這是第 %d 批 / 共 %d 批，整個 repo 有 %d 個檔案 —— **還沒到齊**。"
              % (PART, N_PARTS, TOTAL))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。")
        print("第 1 批裡有檔案清單，貼過它之後每一批都會告訴你還缺哪些。")
        return 0

    if missing:
        print("")
        print("這是第 %d 批 / 共 %d 批。整個 repo 還缺 %d 個檔案 —— 在其他批裡。"
              % (PART, N_PARTS, len(missing)))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。缺的例如：")
        for rel in missing[:6]:
            print("    %s" % rel)
        return 0

    print("")
    print("下一步：")
    print("  cd %s" % dest)
    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ====
#F 4030615f3a785b512d5bf12b223c0b996dfd139e 180 tools/FILELIST.txt
## ADEPT 檔案清單 —— tools/get_code.py 用（每行：git blob SHA-1 + 路徑）。
## 由 tools/make_filelist.py 產生；tests/test_offline_tools.py 會擋住它腐爛。
#f2bf0bd69e5c75960e7038807d0bfbf9474fbebd .github/workflows/ci.yml
#f4af4f7ec449d150841dedb1f4d746658c4e0486 .gitignore
#a1a0c8e12f57e17f7bfbf75f70c3a0d4e91d1e33 AGENTS.md
#a3922dbc6000734e73ea730e8e521f207bb5c8ad CLAUDE.md
#0e34f6c1f9b0afc82d5ffc4b5bba0533aa14a97e README.md
#2a8f038b82940602ac42b1724959afe84d9ae30d SESSION_LOG.md
#650a5d7c8bc6db42eed4054174823bfcfceb7eae adept/__init__.py
#2f6c872448859787dbe6cfba4ef6c2e819d576da adept/__main__.py
#8a51dfe499b3a9d81434c8a202f2d17c24b71c74 adept/core/__init__.py
#bb867d35f598c29094fc4532235e51b959a694fe adept/core/algo/__init__.py
#e86b06ccad3b3981eb4a162d0a99f968fc4fade3 adept/core/algo/align.py
#a77fdc04e961b1cc81f29eb7f200d2d164791e27 adept/core/algo/blob.py
#ed44cb755d91d7f3adf6018672969a6cb68932f0 adept/core/algo/curve.py
#31ed355760ee79e887ddc627c0bc970c77bdfe42 adept/core/algo/enhance.py
#9e85e8aedef61131545e67fef5e323dbb56a5d57 adept/core/algo/glv.py
#a77ccf39e51b71d68671878245eed04422b4f24e adept/core/algo/golden.py
#48cc527868f1d0336d9ed15803aaf54910347842 adept/core/algo/histmatch.py
#9e8715a433ecb84d49151964ed5aea05f8c18dc4 adept/core/algo/normalize.py
#e048c1f3680e5559d0c79d7f080629fecc161549 adept/core/algo/period.py
#d8feeb2677bdd4f54b4fe3ffdd9ee9eeaf6c37e0 adept/core/algo/profile.py
#c8a612c072ba3616d22e6f7b2ae7238bd454c835 adept/core/algo/quality.py
#a9735c3dcf54c6115467af9b4bc3f21838fe58d0 adept/core/algo/roi.py
#ac1c581984cef7d1af53288415f759fb8006172f adept/core/algo/snr.py
#8b94241c23e7cfc64aab9abda16736e476cb08a5 adept/core/algo/stats.py
#04dc4d589bd054b14d86e30bb3a8e8d894128755 adept/core/algo/subpixel.py
#61ccab417e918d137718964b4a6fc9acead1c433 adept/core/algo/template.py
#dcec5abad8375953a68b55b4ac771958207f81bb adept/core/calibration.py
#680d3068c7df905729e015573e65b51c5a96b010 adept/core/export/__init__.py
#801da7f15aff858676f7b2a2826c7c1dc73ecbb7 adept/core/export/klarf_out.py
#eeb80b55a38476ef2f80a5e10538a50bc935aa1b adept/core/export/overlay.py
#2befd3e81601f75aada73c3dc59e2c962f1e64d1 adept/core/export/report.py
#cf4a1ad803592ee09a5fc9c205da267f7de1a3f9 adept/core/ingest/__init__.py
#cd9359f8846e353aad0a7aec2f567dd2c554231b adept/core/ingest/dataset.py
#ddb8939ebee5ba56237cce56d0c53397695982bb adept/core/ingest/imageio.py
#7c83441689fc980b2a4d7e3f46375653ae305054 adept/core/ingest/klarf_core.py
#48bc252f2f4e778f53ebccfd524869e8253b7a6a adept/core/ingest/tiff_index.py
#d138a400e6717b57b9b19187af462d55b6a95100 adept/core/pipeline/__init__.py
#f277b6b3e5e65ce8027da01648a0d42d44a64905 adept/core/pipeline/batch.py
#73f0fec00bdfb78cbd32387e4d890b196e5ce1fb adept/core/pipeline/cache.py
#eaea0e601b87670141d579df99ef562c37f8ae65 adept/core/pipeline/context.py
#8a8f906147c0b06defc52096716ecfd917b0b94e adept/core/pipeline/curve.py
#fa5da5800962d9f5372360e914f440f9601d784d adept/core/pipeline/engine.py
#e8903f84ee1104d66e67f528d0e4ea2951204dea adept/core/pipeline/expression.py
#c75cc58347ed6cb834a0bfab4c4cedc070c96dab adept/core/pipeline/recipe.py
#40461568b5d9317c6d90baf8b02c6bdbfbbb328c adept/core/pipeline/step.py
#fb69a86de270065254eb8c179aebef56f0994ed3 adept/core/steps/__init__.py
#1b6789a92ff01ea44b919be6f91cf07cd6c3391b adept/core/steps/_util.py
#55a5a0bcc01184359f6a4f5bf5aca5c6c99c37d9 adept/core/steps/align.py
#cd0970fe460695f92bd15316a4a5be96f0f5776b adept/core/steps/arith.py
#4e08651dd3cc6c6ca9ebe5c8f8d65cb455f333da adept/core/steps/blob.py
#1d82ef94ad92b93b4e9e023f4a8334fa8394c24c adept/core/steps/cd.py
#2079c270453bebec9f45d2ee524c68afc0a96fb9 adept/core/steps/denoise.py
#afd4fbe9c41c4fdbbee73b53a89626555a1e4dd2 adept/core/steps/flatten.py
#4a209da9d5cab056640d43b23e440a353893b807 adept/core/steps/glv_stats.py
#49a75b01392bbf66e936c2606f7b439b68f9dab9 adept/core/steps/golden.py
#ee3627d1f9b02d3159009077e9b1b2cfc23272c3 adept/core/steps/load.py
#4ef457b2fd7ce6725fce2e2edaea7d83316e8c40 adept/core/steps/normalize.py
#6e906a1610e0dfc2de6ecfee1773cd78652035a2 adept/core/steps/quality.py
#6d7694b11ba4a9a7466b8d9233bcff10db8c5c12 adept/core/steps/region.py
#91d3b4da2de3313df2fadb2ac2015ca5ffa81449 adept/core/steps/roi_profile.py
#f620810659b803d1d9efba0b4ccf6f1c53a92ea1 adept/core/steps/roi_snr.py
#8dcba6fbbf0c970249fc83b0b8e6ac925c07ba74 adept/core/steps/roi_template.py
#9fa9304bcfc700c529e7d9e2f9035120b1e1bc91 adept/core/steps/snr_map.py
#cd57244a5b92565fc110ceee0cccfc6004db10c1 adept/core/steps/tone.py
#0e7d37674a365b4c5292ba728f7da61b0aba6b08 adept/core/store/__init__.py
#9a939964c13156bd41a7eb72b27134921827fb08 adept/core/store/results.py
#e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 adept/ui/__init__.py
#1ce158e532ca3e12af81e66ee60dfc77e8d8b081 adept/ui/app.py
#b69629982f34dd647e5a7ffcee693859f24cadb7 adept/ui/canvas.py
#d90ef40306c61438f189b6a41c48d26e326ed96c adept/ui/export_dialog.py
#7ef762dad06f4a00dc64c0a361c98b83ad86f7a8 adept/ui/gallery.py
#9e2f4b65877a33fb430b18f0093453b650ee3df4 adept/ui/inspectors.py
#40b66dc163f75a9936692ca8bd257143bb9d8359 adept/ui/region_check.py
#fa8845c4baad7e590da0f7190e56d979c8237db5 adept/ui/results.py
#3291d88808ce6ac13388b852978fe9a28f54f016 adept/ui/scope.py
#ad93d9039420c6cd2fac85e498851557ca3a1595 adept/ui/studio.py
#6db287925d828cf8eb2da25433b61659dbbfdc71 adept/ui/template_dialog.py
#ba7b7cf461d0e9837937c1a7bb76d81d39ca300f adept/ui/theme.py
#fd02f73c653fd7aae2756928256e6631a03951bb adept/ui/viewmodel.py
#29edfd5ca497a5e9c4db3d03e9b3f4797da551e4 adept/ui/welcome.py
#75df1028febe3a268f90fd2e4c507f13c5d7ad79 adept/ui/widgets.py
#db4c0723c6a28cddd4c335d5214895f57915fc7d adept/ui/workers.py
#04c5ce471195ac4e2449126ce835b22b4c880cf3 conftest.py
#ba101eee94ed5f8183eba368989167fb1132a128 docs/HANDOVER.md
#08a0584487f2854df1c7796915fbf51f3d90397a docs/NO-GIT-SETUP.md
#b44fd20e599353902ae98f1edc0a1323134d2715 docs/OFFLINE-INSTALL.md
#284baa3b08f76721a95eabc8674130af5fcfa202 docs/plans/F0-master-plan.md
#9cb008460ec1b323254bde1d79e35f33542b401a docs/plans/F7-canvas-and-taxonomy.md
#8dca9d9389fa5413ad9d89cf8ba8c136b7d540e7 examples/recipes/README.md
#f4447ff0a7e92ab5c551c541a165edbcdeec7556 examples/recipes/cd_gate.json
#8f4800382997c2f5e2d5e9fa48e1963184dca10e examples/recipes/die_to_die_basic.json
#cca8e89b079ee63234f5bf8cd4507cf13e9a7911 examples/recipes/dual_route_basic.json
#b20cea5a320e2061621dddc05cec7e48a3ba7bdf examples/recipes/rsem_golden_cell.json
#acc6491ea06d2b61aa63f6c0e1132b24a82f6642 examples/recipes/single_image_rules.json
#e5dde7f87a51c5bc36c04399032cc32447b1a15c fab_probe/README.md
#40ea41a3ba7fc6fb9da08ae90d1624615040b08e fab_probe/probe_klarf.py
#3046145d1bef806353a4b0d63fd81b33347fb8c8 fab_probe/probe_stats.py
#ec0ff843efab0f5474454ada7124f3edd80ae633 fab_probe/probe_tiff.py
#a0efd0dffb6b69c2c67e1801f21528c887b8b763 pyproject.toml
#cf5284f96a1d071e240ef88199e54d580b48c57c requirements.txt
#525a28bc3de17678321715cbca0bdbb60a9a3560 tests/conftest.py
#745560662f263dc8a471f910d8b4640c647dd68d tests/fixtures/sample_real.klarf
#fc105693a52e53f5b37b6c009a1456b9acd8e80f tests/test_align.py
#a0f997191164806f1391e99faad54dc324eb22ab tests/test_batch_cache.py
#1d28c06d3fbd4fabc6456cb942eea6a1db8ea305 tests/test_batch_thread_safety.py
#796aa532ef08b9736a38a00d6232d5d0b5f318e6 tests/test_blob.py
#fce64e2110a74db0e23c9aeda3eec7d2282af53a tests/test_calibration.py
#b6780a2b0cae6b063e177360c5e02a1a3d450948 tests/test_curve.py
#1be97f704f93ae3ebc989a569b9e04cd1de639aa tests/test_dataset.py
#24701f5b8a7c7ee9aecead311645659b5d8a2c72 tests/test_e2e_die_to_die.py
#56c380c7267c6b2f72fb9ac28491cc4952f376e0 tests/test_e2e_dual_route.py
#51947239f318596b8ce7c939c4a42f674cb0a84a tests/test_engine.py
#b9856e4d6846742456149d144c5963d9649d5c27 tests/test_enhance.py
#e640ff60fddb32787660a727ed652bc68971c824 tests/test_example_recipes.py
#2968b33125e3620b1c5ef3c3653d656ba4c76396 tests/test_export_klarf.py
#be9903e176600cc8d742d46b8b89c1aa1039ac2a tests/test_export_overlay.py
#a032dde08875f8b4a7e3d0000cbdbe6aa3c25518 tests/test_export_report.py
#4d9e62f4a9bd01ec28eec1e63e0c395716ad463c tests/test_expression.py
#4017d96f4145ba179d8e186b7f0e02b6e47ed8ef tests/test_fab_probe.py
#862f012efa32c2e2162dd591bb2896cab70145c9 tests/test_glv.py
#2dc56d1e49cf61a990c7e0f9441f3ca99082380c tests/test_golden_step.py
#591460dd7f2ed13dad5ba5aa3337884312e1bfc2 tests/test_histmatch.py
#f99c2421fe691efb20e27f690a066aa2024a325e tests/test_klarf_core.py
#beebe8e22628acc8dff09406c184b3a0ecae0b91 tests/test_klarf_variant_d.py
#66c195b31faf49fd4341defcd22770e86e05c39a tests/test_make_sample.py
#b614d74319ead1329a9b301b5967f2d4d8b5464f tests/test_no_qt.py
#3ca36d76191e3c0c2c801a13720a81874fd847d5 tests/test_no_real_fab_data.py
#f2f18a59cf739942f573f001c64cd77730bc5b09 tests/test_normalize.py
#a1d768507e961ffe06e398c556c8da7a12a6a8ed tests/test_offline_tools.py
#e027a9047fa771cca97915c533a7f90198c0fb18 tests/test_period_golden.py
#482763f96a3f9e39f90a7e6cbd97c6716b29db63 tests/test_phase_origin.py
#8c4b2aba1d0893acc999c5acb331fd00839518d9 tests/test_quality.py
#eff142e969dcbb7b7234677b6b5398fc0d3039b1 tests/test_recipe.py
#ec7a355551b68c41ad5513d1e1a287f7ae5e506d tests/test_region.py
#f6565ccc073a5846b9e3a5b66961131e4e797c72 tests/test_results_store.py
#16cd9995a97eb6b919044e2c72fe1bcddb954e2a tests/test_roi.py
#5994f7e6af5733d16ddd4ac0c0df62f9bcf8a07f tests/test_roi_profile.py
#a7c41debc132957219cb7a9187a4cb7efe1d3317 tests/test_roi_template.py
#ecb57644cec348b3ef52d811332dd9c353fcd920 tests/test_rsem_ingest.py
#99687acf0a8aae0d2c88f7fca293cfad2e31c7b5 tests/test_snr.py
#29cdd488b75b074bd0588375762629a26d941b77 tests/test_stats.py
#dd89a3a0ca71cd8d0cfe69f5ee82fd430e723fb3 tests/test_steps.py
#38d2a7f3b7731f16b92155e49775746815f30fc6 tests/test_subpixel.py
#605fe6f103ffff4b761e33a8fde8fd52db79c1b9 tests/test_tiff_index.py
#05e63f22247d0bf597c925909c0cc2f548fbe648 tests/test_ui_canvas.py
#4cc9539773183626bf0e94f8cfeb5453ababd42e tests/test_ui_controls_readable.py
#46c837b6f362d0493860e0cc4e657fecfabeea2d tests/test_ui_english_only.py
#e07df332dae100f630b92b760386e85bb4c729a0 tests/test_ui_export_dialog.py
#877d92d66b6b539947142476b9d7d8bd6f32c9a8 tests/test_ui_f7_10_route_edges.py
#5f9141042b4721854e37278486c382f72059a412 tests/test_ui_f7_11_roi.py
#ea1cdea68a91e2c08fb2bef0cede55e44f2ff574 tests/test_ui_f7_12_template.py
#f310008decc0246abe0bf5dd54218a96f260c3d4 tests/test_ui_f7_14_canvas_flow.py
#fed44e36372c1523c663aa065a9ae0712544ba25 tests/test_ui_f7_15_reading_load.py
#ce33115c49f3805c216293d1ef63006cd91469ae tests/test_ui_f7_16_safety_net.py
#66018acf8f0ef2cbfc99f16fbe215160a30e66d6 tests/test_ui_f7_17_inspectors.py
#b6820cf88fdb6a7b7951dc0c3ca2ee2255a9a296 tests/test_ui_f7_18_streams_as_nodes.py
#a1f0bb8a312afacd04eb4394b244519e632c0790 tests/test_ui_f7_9_feedback.py
#500bc2445ff7f460b63e56345d22c9d43048aaca tests/test_ui_gallery.py
#1ddeef396181f9eabfcf63a5cbd7af119a54c75a tests/test_ui_patch_only.py
#11503b28be232ab36fd8201512275150e26969e0 tests/test_ui_results.py
#48e047f2ce44c7ad2990f8467035d53fa2b6fc45 tests/test_ui_studio_m5.py
#228a8663a093edb280b6faa5608db83c5c94a61e tests/test_ui_studio_smoke.py
#37f2c567d7962f3aa2e851ab6c5fe8b9821901bd tests/test_ui_welcome.py
#efeac6b931bea95d7e0f392c0e36e5bd9056e410 tests/test_ui_widgets.py
#a58940d76a6ddb0c6fede04f4f8912e3b3426825 tests/test_ui_workers.py
#24571931e3aa73f5caded9462396fe1aa3b49589 tests/test_viewmodel.py
#7686c156f22af29465ce3a73caf617df4bafad77 tools/_synth.py
#f8c1eef367e78983dd4b33d8a4a7a485366070d6 tools/check_files.py
#6e7239f088a5a140f56ba29f2269b5295b75aecf tools/doctor.py
#eac9fb372e5230539a81868e667bd6c850362a71 tools/fetch_wheels.py
#d3c3fa7d8b3e0d6a3605a585a67c45d0b6aa650d tools/get_code.ps1
#4d8a556b49b3c29df3e14b975225082e4c8a948d tools/get_code.py
#ad250d60c5c5f97e757842046c23816230704ef1 tools/install_offline.py
#79318988a82fb09aa02a79cea32db78f966855b4 tools/make_filelist.py
#a096a20ac78fba6911826946334eb6ad2227ec23 tools/make_sample.py
#cd11d6aba3d087b6d30ea50e385fd44f3586f865 tools/make_sample_rsem.py
#c078e47ba2a10ef1c380da1d54aea9cb0ca62fe4 tools/make_text_bundle.py
#
#F f2bf0bd69e5c75960e7038807d0bfbf9474fbebd 65 .github/workflows/ci.yml
#name: tests
#
#on:
#  push:
#    branches: [main]
#  pull_request:
#  workflow_dispatch:
#
#jobs:
#  test:
#    runs-on: ubuntu-latest
#    strategy:
#      fail-fast: false
#      matrix:
#        python-version: ["3.9", "3.11", "3.12"]
#
#    steps:
#      - uses: actions/checkout@v4
#
#      - uses: actions/setup-python@v5
#        with:
#          python-version: ${{ matrix.python-version }}
#          cache: pip
#
#      - name: Install system deps for Qt (offscreen)
#        run: |
#          sudo apt-get update
#          sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3 \
#                                  libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
#                                  libxcb-shape0 libxcb-xinerama0
#
#      - name: Install Python deps
#        # 這一行是 requirements.txt 的鏡像，只換一個東西：opencv-python ->
#        # opencv-python-headless（runner 上沒有顯示裝置）。**加相依套件時兩邊都要改** ——
#        # 下面那一步會擋住漏掉的情況。
#        run: |
#          python -m pip install --upgrade pip
#          pip install numpy opencv-python-headless tifffile PySide6 openpyxl pytest
#
#      - name: Check the install list still covers requirements.txt
#        # openpyxl 曾經漏在這裡：requirements.txt 有、CI 沒有，於是 Excel 匯出
#        # 的測試在 CI 上失敗而本機全綠。與其靠人記得，不如讓 CI 自己發現。
#        run: |
#          python - <<'EOF'
#          import re, sys, importlib.util
#          names = []
#          for line in open("requirements.txt", encoding="utf-8"):
#              line = line.strip()
#              if line and not line.startswith("#"):
#                  names.append(re.split(r"[<>=!~\[]", line, 1)[0].strip())
#          # 匯入名稱與套件名不一樣的例外
#          IMPORT_NAME = {"opencv-python": "cv2", "PySide6": "PySide6"}
#          missing = [n for n in names
#                     if importlib.util.find_spec(IMPORT_NAME.get(n, n)) is None]
#          if missing:
#              sys.exit("requirements.txt lists %s but CI did not install them; "
#                       "add them to the 'Install Python deps' step." % missing)
#          print("all of requirements.txt is importable:", names)
#          EOF
#
#      - name: Run tests
#        env:
#          QT_QPA_PLATFORM: offscreen
#        run: pytest -q
#
#F f4af4f7ec449d150841dedb1f4d746658c4e0486 16 .gitignore
#__pycache__/
#*.pyc
#.pytest_cache/
#build/
#dist/
#*.egg-info/
#.venv/
#
## ADEPT runtime artefacts
#*.db
#*.npz
#/cache/
#
## 離線安裝 wheels（各機器自行取得，不進版控）
#wheels/
#
#F a1a0c8e12f57e17f7bfbf75f70c3a0d4e91d1e33 117 AGENTS.md
## AGENTS.md — 開發環境與限制
#
#給任何要在這個專案上動手的人／agent。**先讀這一份**，再讀
#[`CLAUDE.md`](CLAUDE.md)（怎麼動手）與 [`docs/HANDOVER.md`](docs/HANDOVER.md)
#（為什麼長成這樣）。
#
#這一份講的是**環境**：這個專案在什麼樣的機器上開發、在什麼樣的機器上執行，
#以及那些限制怎麼決定了程式碼的形狀。不知道這些的話，很多設計看起來是多餘的
#（為什麼工具都是 stdlib-only？為什麼有三種取得程式碼的方式？為什麼有個
#`FILELIST.txt`？），然後就會被「順手簡化」掉。
#
#---
#
### 1. 兩台機器
#
#開發與執行**不在同一台機器上**，而且兩台的限制正好互補：
#
#| | 家用機（開發） | 公司機（執行） |
#|---|---|---|
#| git | ✅ | ❌ 不能裝、不能執行 git 操作 |
#| 網路下載 | ✅ 什麼都能下載 | ❌ **目前什麼都下載不了**（`.zip` 被擋、`.py` 也被擋）|
#| 看得到 GitHub 網頁 | ✅ | ✅ **看得到檔案內容，而且可以按複製鈕** |
#| 執行 `.py` | ✅ | ✅ |
#| `pip install` | ✅ | ✅ 走**公司內部 PyPI 鏡像**（不是 proxy）|
#| PowerShell | ✅ | ✅ |
#| **真實資料** | ❌ **沒有** | ✅ **只有這裡有** |
#
#最後一列是關鍵：**開發的地方沒有資料，有資料的地方不能開發。**
#
#### 這件事的後果
#
#- **全部功能都要能用合成資料開發與驗證。** `tools/make_sample.py` /
#  `make_sample_rsem.py` 不是玩具，它們是唯一的開發資料來源。
#  新功能如果只能用真實資料驗證，那它在家用機上就無法驗證 —— 設計要繞開這件事。
#- **真實資料的假設必須「可探測」而不是「假設對了就好」。** 這就是 `fab_probe/`
#  存在的理由：三支 stdlib-only 的單檔腳本，複製到公司機上跑，輸出純文字、
#  預設遮蔽識別碼，所以結果可以貼回開發端。見 `CLAUDE.md` §8 的三個待驗證假設。
#- **不能有「只在公司機上才能跑的建置步驟」。** 公司機不能下載東西，所以任何
#  「執行前要先抓什麼」的設計都是死路。
#
#---
#
### 2. 唯一的傳輸通道是剪貼簿
#
#公司機下載不了東西，但**看得到 GitHub 上的檔案並且可以複製**。所以程式碼進去的
#方式是：**在瀏覽器打開檔案 → 按右上角的複製鈕 → 貼進記事本 → 存成檔案**。
#
#這條通道有兩個硬限制，設計必須繞開：
#
#1. **GitHub 不顯示超過 1 MB 的檔案。** 太大的檔案在那台機器上根本點不開來複製。
#   所以搬運用的包一定要分批（`bundle/` 裡每一批 < 420 KB）。
#   「打包成功但送不進去」是最糟的一種「做完了」。
#2. **一次複製一個檔案。** 176 個檔案不可能一個一個貼，所以要有整包的形式；
#   但更新的時候也不該重跑整套搬運，所以要有「只有這幾個變了」的機制。
#
#### 三條路，用在不同的時機
#
#| 情況 | 用什麼 | 成本 |
#|---|---|---|
#| **第一次搬整包** | `bundle/ADEPT_part1of6.py` … `part6of6.py`，每一批貼進去執行一次 | 6 次複製 |
#| **之後更新** | 複製 `tools/FILELIST.txt`（12 KB）→ `python tools/check_files.py` → 它列出要重新複製哪幾個 | 1 次小複製 + 幾次針對性複製 |
#| **只想跑格式探測** | 直接複製 `fab_probe/probe_*.py`（各 24–46 KB，stdlib-only 單檔，**不需要整個 repo**） | 1–3 次複製 |
#
#最後一條常被忽略：要驗證 `CLAUDE.md` §8 那三個假設，**不需要搬整個專案**。
#
#### 網路真的通的時候還有兩支
#
#如果哪天 proxy／allowlist 放寬了，`tools/get_code.py`（Python）與
#`tools/get_code.ps1`（PowerShell）可以逐檔抓下來，不必手動複製。
#它們目前在這個環境下**過不了 proxy**，但寫進來的診斷是有用的資產 ——
#連線失敗分六種，每一種的處置都不一樣（見 `docs/NO-GIT-SETUP.md`）。
#
#---
#
### 3. 這些限制決定了哪些程式碼形狀
#
#看到下面這些東西的時候，**它們不是過度設計，是上面那些限制的直接後果**：
#
#| 設計 | 為什麼 |
#|---|---|
#| `tools/` 底下每一支都是 **stdlib-only** | 它們要在「套件還沒裝好」或「根本裝不了」的機器上跑。有測試（`test_offline_tools.py`）掃 module-level import 把這條鎖住 |
#| **Python 3.9 相容語法** | 公司機的 Python 版本不由我們決定。測試用 `ast.parse(feature_version=(3,9))` 掃全套件 |
#| 整個 repo **只有純文字檔** | 剪貼簿通道只搬得動文字；而且純文字才能在 GitHub 上被看到與複製 |
#| `tools/FILELIST.txt`（git blob SHA） | 「哪幾個檔案變了」的唯一依據。它腐爛的代價是**公司機上安靜地少一個檔案** |
#| 每一種搬運方式都**驗 SHA** | 剪貼簿與 proxy 都可能安靜地改掉內容（截斷、換行、攔截頁）。驗不過就不落地 |
#| `bundle/` 裡有產生出來的複本 | 那是搬運品，不是內容。**已刻意排除**在 `FILELIST.txt` 與打包來源之外（不然會遞迴長大） |
#| **repo 裡不得有廠內識別碼**（鐵則 8）| 這個 repo 是 public，而它是唯一的傳輸通道 —— 資料只能往「進公司」的方向走，不能往外 |
#
#---
#
### 4. 每次改動之後要做的兩件事
#
#```bash
## 1. 檔案清單（新增/刪除檔案之後；順序是 git add 之後才跑）
#git add -A && python tools/make_filelist.py && git add -A
#
## 2. 只有在要搬進公司機之前才需要重打包（會動到 6 個大檔案）
#python tools/make_text_bundle.py --out bundle/ADEPT.py --split 400
#```
#
#第 1 件有測試守著（忘了跑會紅）。第 2 件**刻意沒有自動化** ——
#`bundle/` 裡是 2.4 MB 的複本，每次 commit 都重產會讓 diff 變成噪音。
#需要搬運的時候才跑。
#
#---
#
### 5. 開發流程本身
#
#見 [`CLAUDE.md`](CLAUDE.md) §6。測試在家用機上跑：
#
#```bash
#QT_QPA_PLATFORM=offscreen python -m pytest -q       # Windows 不用設那個變數
#```
#
#一個環境上的注意事項：UI 測試在**單一行程裡跑整套**會累積 Qt 記憶體而變得極慢
#（容器裡實測會從 100 秒變成十幾分鐘）。分段跑就正常。這不是測試的問題。
#
#F a3922dbc6000734e73ea730e8e521f207bb5c8ad 369 CLAUDE.md
## CLAUDE.md — ADEPT 開發指南
#
#給 Claude Code / 開發者的專案脈絡（操作手冊）。
#**每次 session 結束請更新 `SESSION_LOG.md`。**
#
#> **第一次接手這個專案？三份文件，先讀前兩份。**
#>
#> - **[`AGENTS.md`](AGENTS.md) —— 環境。** 開發在家用機、執行在公司機，兩台的
#>   限制正好互補：**有真實資料的那一台不能裝 git、目前什麼都下載不了**，
#>   唯一的傳輸通道是「在 GitHub 上看到檔案、按複製鈕」。不知道這些的話，很多
#>   設計看起來是多餘的然後就會被「順手簡化」掉 —— 為什麼 `tools/` 全是
#>   stdlib-only、為什麼有 `FILELIST.txt`、為什麼有 `bundle/`。
#> - **[`docs/HANDOVER.md`](docs/HANDOVER.md) —— 為什麼長成這樣。** 工具的由來與
#>   目的、需求訪談的結論與理由、六個來源專案各給了什麼（那份跨專案脈絡不在
#>   程式碼裡）、哪些事已驗證哪些還是假設、哪些設計「看起來可以隨便改但其實有
#>   理由」。
#> - **這份 CLAUDE.md —— 怎麼動手。**
#
#---
#
### 1. 這是什麼
#
#**ADEPT** = Auto Defect Evaluation Pipeline Tool。
#半導體 E-beam Inspection 的彈性 ADC 工具：讀 patch/RSEM 影像 + KLARF，
#用「步驟卡片組 pipeline」對每顆 defect 算分、分 bin、寫回 KLARF。
#
#**最高指導原則：站點差異封裝進 recipe，不封裝進程式碼。**
#第二原則：**推廣鐵則** —— 目標使用者是不會寫 code 的製程/設備工程師。
#任何讓他們看不懂或會爆錯誤訊息的設計，都是 bug。
#
#---
#
### 2. 心智模型：三段式
#
#```
#【影像段 Image】把圖變乾淨、變可比  → 產出「影像流」（ctx.images）
#        ↓
#【算法段 Algo】 從圖量出數字（量化證據）→ 產出「特徵」（ctx.features）
#        ↓
#【ADC 判定段】 features → score → bin → 寫回 KLARF
#```
#
#**注意（F7-3 起）**：上面的三段是 `Step.category` —— **引擎**的分類
#（快取切點、驗證順序）。**使用者看到的**分組是另一個軸 `Step.group`：
#
#```
#Input → Enhance → Region → Compare → Measure → ADC
#```
#
#因為 category 描述的是「這張卡吐什麼型別」，不是「使用者想解決什麼問題」。
#兩個軸各有各的用途，不要合併。新卡片放哪一組：看它吃什麼、吐什麼
#（規則寫在 `pipeline/step.py` 的 `GROUP_*` 常數旁邊）。
#
#UI 三段分色（影像=藍 `#6f93b5`／算法=橙 `#c06a1d`／判定=紫 `#8a6fb5`）。
#這個分類不是裝飾 —— 它同時是 `Step.category`、快取切點、recipe 驗證順序的依據。
#
#---
#
### 3. 目錄結構
#
#```
#adept/
#├── core/                    # 純運算，**禁止任何 Qt import**（tests/test_no_qt.py 守門）
#│   ├── ingest/              # KLARF + 影像載入
#│   │   ├── klarf_core.py    #   KLARF 1.2/1.8 無損讀寫引擎（vendored from KLIP，最重要的資產）
#│   │   ├── tiff_index.py    #   免解碼 TIFF/BigTIFF 盤點 + tifffile 讀 page
#│   │   ├── imageio.py       #   CJK-safe 影像讀寫（np.fromfile + cv2.imdecode）
#│   │   └── dataset.py       #   ebi_patch / rsem / folder 自動判別 → DefectItem
#│   ├── algo/                # 純 numpy/cv2 演算法（step 卡片包這些，不要在卡片裡重寫數學）
#│   ├── pipeline/            # 引擎
#│   │   ├── context.py       #   Context（images/features/meta）—— 步驟間的唯一介面
#│   │   ├── step.py          #   Step 介面 + ParamSpec + registry
#│   │   ├── recipe.py        #   Recipe(DAG) + lint 式 validate
#│   │   ├── expression.py    #   score 表達式引擎（自寫 parser，不用 eval）
#│   │   ├── engine.py        #   單顆執行 + checkpoint 快取版
#│   │   ├── batch.py         #   ProcessPool 平行批次
#│   │   └── cache.py         #   影像段 checkpoint 快取（npz）
#│   ├── steps/               # 步驟卡片（每檔一類）
#│   ├── store/               # SQLite 批次歷史 + rescore
#│   ├── export/              # KLARF 三種寫回模式 + CSV/Excel 報表 + overlay
#│   └── calibration.py       # nm/px 校正 profile
#├── ui/                      # PySide6 Studio（**唯一允許 Qt 的地方**）
#│   ├── scope.py             #   產品範圍開關：目前只吃 EBI patch（F7-1，見 §11）
#│   ├── viewmodel.py         #   RecipeModel（Qt-free，可 headless 測；含 edges）
#│   ├── canvas.py            #   節點畫布（n8n 式；F7-6，純 UI，引擎零改動）
#│   ├── results.py           #   Results 視窗：直方圖 + Gallery + 輸出（F7-5）
#│   ├── region_check.py      #   區域跨顆檢視：框畫在 N 顆縮圖上（F7-11）
#│   ├── template_dialog.py   #   從大圖疊 Golden Cell 模板（F7-12；模板存進 recipe）
#│   ├── inspectors.py        #   每張卡自己的儀表（F7-17；依 Step.key 註冊）
#│   ├── theme.py widgets.py  #   主題 token + 6 個資料驅動元件
#│   ├── gallery.py           #   同屏比多顆（虛擬捲動，撐 10k+）
#│   ├── welcome.py           #   首啟導覽 + 範例 recipe 庫對話框
#│   ├── export_dialog.py     #   輸出精靈（寫回前一定先預覽變更）
#│   ├── workers.py           #   載入/預覽(請求合併)/試跑 背景執行緒
#│   └── studio.py app.py     #   主視窗 + 進入點
#├── tests/                   # 520+ 個測試，全部用合成資料，~30s 跑完
#├── tools/                   # make_sample(_rsem).py 合成資料；離線安裝三件套：
#│                            #   fetch_wheels.py（有網路的機器抓）→ install_offline.py
#│                            #   （air-gapped 機器裝）→ doctor.py（環境自檢）
#├── examples/recipes/        # 範例 recipe（也是 UI「載入範本」的來源）
#├── fab_probe/               # 廠內格式探測腳本（stdlib-only、純文字輸出），見 §8
#└── docs/plans/              # F0 = master plan；每個 milestone 一份
#```
#
#---
#
### 4. 鐵則（違反 = 測試會擋）
#
#1. **`adept/core` 不得 import Qt**。UI 只透過 callback 與 core 互動。
#2. **Python 3.9 相容語法**（廠內機器可能是舊版）。測試以 `ast.parse(feature_version=(3,9))` 掃全套件。
#3. **每個 ParamSpec 的 `help` 必填**且要是白話。`register_step` 會拒絕沒有 help 的卡片。
#4. **每個 Step 要有合理 default 與 min/max**。使用者填爆的值必須擋在 `validate_params`，
#   不能讓它跑到演算法裡炸。
#5. **檔案寫入一律 atomic**（`.tmp` + `os.replace`）。
#6. **KLARF 寫回必須無損**：沒被改到的 byte 要與原檔逐位元組相同（`klarf_core` 的 span-splice）。
#7. **單顆 defect 出錯不得殺掉整批**（`run_defect` 從不 raise，回 `ok=False`）。
#8. **repo 裡不得有未遮蔽的廠內識別碼**（Lot／Wafer／機台／device／recipe 名稱／
#   廠區代號／缺陷分類名稱）。測試 fixture 也一樣 —— 它們斷言的是**結構**，
#   值遮蔽掉一條測試都不會壞。`tests/test_no_real_fab_data.py` 會擋。
#
#---
#
### 5. 加一張新卡片（最常見的工作）
#
#```python
## adept/core/steps/my_card.py
#from ..pipeline.context import Context
#from ..pipeline.step import CATEGORY_ALGO, ParamSpec, Step, StepError, register_step
#
#@register_step
#class MyCardStep(Step):
#    key = "my_card"                    # recipe JSON 用的 id
#    label = "我的卡片"                  # UI 顯示
#    category = CATEGORY_ALGO           # image / algo / adc
#    help = "一行白話：這張卡做什麼。"      # 必填
#    params = [
#        ParamSpec(name="source", type="image_key", default="diff",
#                  help="要分析哪個影像流。"),
#        ParamSpec(name="k", type="int", default=3, min=1, max=99,
#                  help="視窗大小（越大越平滑）。"),
#    ]
#    reads = ["diff"]; writes = []; features_out = ["my_metric"]
#
#    def run(self, ctx: Context, params):
#        p = self.validate_params(params)
#        img = ctx.require_image(p["source"])       # 缺影像會拋帶說明的 ContextError
#        ctx.add_feature("my_metric", float(...))   # 演算法請呼叫 adept.core.algo.*
#        return ctx
#```
#
#`steps/__init__.py` import 它即完成註冊 —— **UI 與引擎零修改**，卡片庫自動出現。
#param 相依 I/O（例如輸出流名稱由參數決定）覆寫 `resolve_reads/resolve_writes/resolve_features`。
#
#> **一張卡只做一條影像流**（F7-18）。Enhance 卡吃 `target`（或 `source`）一條流、
#> 寫回同一條，`resolve_writes` 就只回那一條。要對 ref 也做同一件事就**再放一張卡**
#> —— 「要對哪幾張圖做」是畫布上的事（哪條線接進來），不是控制列上的一組勾選框。
#> 一張卡寫兩條流會讓畫布說謊：它畫在 test 那條鏈上，卻同時改寫了 ref。
#> 需要「借另一條流的資訊」時，那件事要有自己的參數（例：`percentile_norm` 的
#> `range_from`），而且型別是 `image_key` —— 它在畫布上就是第二條接進來的線。
#
#> **參數名是 recipe 的鍵，不是給人看的字**（F7-9）。`ParamSpec` 有選填的
#> `label`：有就顯示 label，沒有就顯示 `name`。`range_from` 對製程工程師不是
#> 一句話，`Borrow range from` 才是。同理，「一串影像流」請用 `type="image_keys"`
#> 而不是 `str` —— 值的格式一樣（逗號分隔字串），但 UI 會給上游每一條流一個
#> 勾選框，使用者不必猜能填什麼，也不會打錯字。
#
#> **把 `min`/`max` 填好，滑桿是免費的**（F7-8）。ParamForm 看到有上下界的
#> `int`/`float` 就自動配一支跟數字框雙向綁定的滑桿。這不只是好看 ——
#> 使用者是一邊拖一邊看影像決定值的，「先想好一個數字再輸入」那個順序是反的。
#> `type="curve"` 則會拿到一張可以自己拉的色調曲線編輯器（見 `pipeline/curve.py`）。
#
#---
#
### 6. 開發流程
#
#```bash
#python -m venv .venv && .venv\Scripts\activate      # Windows
#pip install -r requirements.txt && pip install pytest
#
#QT_QPA_PLATFORM=offscreen pytest -q                # 全部測試（Windows 不用設 QT_QPA_PLATFORM）
#python tools/make_sample.py /tmp/lot --n 100       # 產合成資料
#python -m adept gui                                # 開 Studio
#python -m adept run examples/recipes/die_to_die_basic.json /tmp/lot/LOT_SYN.001 \
#    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
#```
#
#**新增或刪除檔案之後**要更新受限機器用的檔案清單（順序是 `git add` 之後才跑，
#因為它讀的是 `git ls-files`）：
#
#```bash
#git add -A && python tools/make_filelist.py && git add -A
#```
#
#`tests/test_offline_tools.py` 會擋住那份清單腐爛 —— 忘了跑的話，那個檔案在
#「下載被擋、只能用剪貼簿搬」的機器上會**安靜地少掉**（見 §9.5 與 `AGENTS.md`）。
#
#**要把程式碼搬進公司機之前**才需要重打包（會動到 `bundle/` 底下 6 個大檔案，
#所以刻意不自動化 —— 每次 commit 都重產會讓 diff 變成噪音）：
#
#```bash
#python tools/make_text_bundle.py --out bundle/ADEPT.py --split 400
#```
#
#新功能請開 `docs/plans/F<n>-<name>.md`（沿用 GLAS/MMH 慣例），完成後更新 `SESSION_LOG.md`。
#
#---
#
### 7. 已知的坑（踩過，別再踩）
#
#| 坑 | 症狀 | 解法 |
#|---|---|---|
#| **fork 死鎖** | GUI 按「試跑」永遠不回、progress 一格不動 | `batch._pool_context()`：主執行緒 fork、非主執行緒 spawn。改動這裡務必跑 `tests/test_batch_thread_safety.py` |
#| **OpenCV IPP 非決定性** | 同張圖算兩次差 ~1e-8，快取結果對不起來 | `batch.pin_cv2_deterministic()` 關 IPP（每個 worker 都呼叫） |
#| **Fusi³ ecc 對位正負號** | ecc backend 位移與其他四個相反 | 已於 `algo/align.py` 修正並鎖測試 |
#| **MMH 次像素 batch 版偏移** | batch 版比 scalar 版低約 1.5 px | 刻意保留原行為，檔頭有記錄；要用精確值請用 scalar 版 |
#| **中心框幾何與影像尺寸綁死**（F7-4 已修） | 同一組 `glv_stats` 參數在 128² patch 上準、在 256² RSEM 上漏抓（缺陷散佈超出框） | **幾何已從量測卡搬到 Region 卡**（`roi_define`），量測卡只引用 ROI 名字。`size_unit="percent"` 的框會隨影像尺寸縮放，同一份 recipe 換 patch 尺寸不會失效。迴歸測試 `tests/test_region.py::test_percent_sizing_survives_a_patch_size_change` |
#| **pytest 收集期 import Qt** | `test_no_qt_after_import` 失敗 | UI 測試一律 **lazy import**（在 fixture 內 import 並注入 globals） |
#| **`QGraphicsItem` 拖曳留殘影**（F7-8 已修） | 拖動節點時埠標籤（"test"/"ref"）的舊位置沒被清掉 | `boundingRect()` **必須涵蓋所有畫得出去的東西**。埠標籤畫在節點右緣之外，之前只算到 `NODE_W + _PORT_R`，Qt 就只重繪那個範圍 |
#| **在節點外面畫東西**（F7-8／F7-9／F7-14 同一條） | 拖動節點留殘影 | `boundingRect()` 必須涵蓋**所有畫得出去的東西** —— 埠標籤（F7-8）、埠圓點（F7-9）、輸出埠的 `+`（F7-14）都在節點右緣之外。加任何畫在卡片外的裝飾時，先把 `boundingRect` 加寬，`tests/test_ui_f7_14_canvas_flow.py` 會斷言 `+` 的中心在 `boundingRect` 裡 |
#| **`paint()` 用場景座標**（F7-9 已修） | 殘影**又**出現；而且「新增的節點只有左邊有圓框，右邊沒有」 | 兩個症狀同一個因：`paint()` 拿 `out_anchors()`（**場景**座標）去畫本地座標的東西。節點在原點看起來正常（第一欄的 Input 剛好在那）；一離開原點就畫到「兩倍位移」的位置。現在分成 `out_anchors_local()`（繪製／命中）與 `out_anchors()`（連線）。F7-8 只放大了 `boundingRect`，那是對症狀動刀 —— 真正的不變量是**畫的座標系＝宣告的座標系**，`tests/test_ui_f7_9_feedback.py` 直接鎖它 |
#| **`test_no_qt_after_import` 跟檔名字母序有關**（F7-9 已修） | 新增一支 UI 測試檔就讓它失敗，而且失敗訊息指不到真正的原因 | 它以前在測試行程裡看 `sys.modules`，所以任何排在 `test_no_qt.py` **之前**的 UI 測試檔跑過 fixture 之後就會誤報。改成在乾淨的子行程裡 import core 再問 —— 那本來就是這條測試唯一想問的事 |
#| **快取只存了 Context 的一部分**（F7-9 已修） | 同一份 recipe **第一次跑對、第二次跑錯**（`region 'main' is not defined`） | checkpoint 是執行順序上的**位置**（最後一張影像段卡的下一格），不是「所有影像段的卡」，所以夾在中間的 Region 卡（algo）會落在快取段裡。v1 快照只存 images/features/meta，`ctx.rois` 命中時整個不見。快照現在涵蓋 `rois` 與 `labels`，並帶 `FORMAT_VERSION`（版本不合一律當 miss，舊快取目錄不會餵回殘缺快照）。迴歸測試 `tests/test_batch_cache.py::test_named_rois_survive_a_cache_hit` |
#| **特徵是扁平的全域命名空間**（F7-11 已解） | 兩張同型別的量測卡（例：量兩個 ROI 的 `glv_stats`）都寫 `glv_mean`，後面那張**安靜地蓋掉**前面那張，分數表達式指不到前面那個值 | 量測卡有 `output_prefix`（Studio 挑了區域會自動填成區域名），撞名時 `validate()` 仍會出 `feature-collision` warning、Studio 跑完在狀態列講出來 |
#| **量測卡指到沒人定義的 ROI**（F7-9 已修） | `cd_measure` 預設 `roi="blob"`，少了上游 Blob 卡時**安靜地改量整張圖** —— 跑得完、有數字、而且是錯的 | 具名區域現在跟影像流走同一條檢查：`Step.resolve_regions_in/out()` + `validate()` 的 `unknown-region`；`blob` 退回整張圖時會 `ctx.warn`。Studio 也在試跑前先跑 lint（以前完全沒跑，於是接錯的卡片會「跑完 200 顆、每顆都失敗」） |
#| **色調曲線用自然三次樣條** | 使用者把中間點往上拉，影像出現一圈**不存在的暗環** | 樣條會 overshoot。`algo/curve.py` 用保單調三次 Hermite（Fritsch–Carlson）。這是演算法自己造出來的假缺陷 —— 對判 defect 的工具是最糟的一種 bug。`tests/test_curve.py` 用四條最容易凹出去的曲線鎖住 |
#| **`isVisible()` 在 show 之前恆為 False** | 「這個面板收起來了嗎」在建構期永遠答錯 | 一律追明確狀態（`LibraryPanel.panel_open()`、`StudioWindow.compare_enabled()`、`_progress_on`），不要問 widget |
#| **`drawPolygon` 傳散的 `QPointF`**（F7-17） | 整個行程 **segfault**（不是丟例外，所以看不到任何訊息，只有 exit 139） | PySide6 會綁到別的 overload。要傳 `QPolygonF([...])`。自繪面板加任何多邊形時注意 |
#| **暗色盤裡的佔位字串**（F7-17 已清） | `accent_border` 的值是 `"#2f4straight"`，靠 70 行後的一句覆寫救著 | Qt 對無效色字串是**靜靜畫成黑色**，不會報錯。色盤裡不要留「稍後修正」的值；`tests/` 有一條掃描所有 token 是否為合法 hex |
#| **`_update_action_states` 會蓋掉 tooltip**（F7-16 已修） | 把快捷鍵寫進工具列 tooltip，第一次 refresh 之後就不見了 | 那幾顆的 tooltip 每次 refresh 都會依前置條件重寫（「還沒有東西可以存」）。所以不能「建構時附加一次」，要讓**設 tooltip 的那個動作自己補上快捷鍵**（`_set_tip`）。`test_ui_f7_16_safety_net.py` 會 refresh 一次再驗 |
#| **Qt 的 Enter/Leave 在父子之間會打架**（F7-15 已修） | 滑鼠從參數列的空白處移進**那一列自己的**輸入框，說明就閃一下（收起來又立刻攤開） | Qt 先送 `Leave` 給父元件、再送 `Enter` 給子元件。照字面處理必閃。`leaveEvent` 改成直接問**游標還在不在自己的矩形裡**（`rect().contains(mapFromGlobal(QCursor.pos()))`），不要相信事件的字面意思 |
#| **QSS 把 subcontrol 的箭頭畫成 0 個畫素**（F7-13 已修） | 下拉選單跟自由文字框**長得一模一樣**，使用者無從得知哪個點得開（`Match on` vs `Name this region`） | `QComboBox::drop-down { border: 0 }` —— styled 的 subcontrol 要**自己提供 `down-arrow` 圖檔**，否則 Qt 什麼都不畫，而這個 repo 是純文字的（§9.5）塞不了圖。拿掉 `border: 0` 讓它留在 base style 上。`tests/test_ui_controls_readable.py` 用畫素數量鎖住（箭頭區 0 → 20，而 QLineEdit 恆為 0） |
#| **參數合法 ≠ 設定完成**（F7-13 已修） | 空模板是完全合法的 str，lint 沒話說 —— 但那張卡跑起來**每一顆**都失敗，而使用者是跑完 200 顆才知道 | `Step.configuration_issues(params)`：卡片自己講缺什麼、用**這張卡的話**講（要去按哪顆鈕），變成 lint error `not-configured`，畫布上那張卡右上角掛警示標記。加這種卡時記得：`test_every_visible_card_can_be_wired_up_without_a_dead_end` 會要求訊息**指得出路在哪** |
#| **模板比對：分數本身會騙人**（F7-12） | 全白／純雜訊的 patch 對任何模板都能拿到 NCC 0.44（門檻 0.3 → 過關），於是「碰巧」被當成「對得準」，框放到隨機的位置 | **沒有任何分數門檻分得出這兩者**（分數重疊）。要問的是另一個問題：**這張 patch 自己有沒有東西可比**（`min_structure`，實測無結構約 1、有結構 20 以上）。另外 margin 必須**先把比對曲面折回一個週期**再取次高峰，否則相鄰週期的次高峰讓 margin 恆為 0 —— 週期性把自己打敗了 |
#| **Golden Cell 的原點會飄**（F7-12） | 同一份 recipe、不同時間建的模板指到不同的地方，而且畫面上完全看不出來 | cell 的第 0 欄預設是大圖上的**任意切點**，換張圖就換了 —— 而使用者是在 cell 上標框的。`algo/template.py::anchor_cell()` 旋轉到**最強的上升邊**在第 0 欄；用最大正梯度而不是 `abs`，否則一個週期的兩個相反邊界會競爭，錨點在兩者之間跳 |
#| **`estimate_period` 在純雜訊上會回一個看似合理的週期**（F7-12） | 噪音圖疊出一個沒有意義的模板，然後安靜地拿去對每一顆 | 週期信心門檻 `MIN_PERIOD_CONFIDENCE = 40`（實測噪音 20.3）。「說我做不到」比「給一個沒有意義的答案」好得多。順帶：一維 layout（垂直條紋，只有 X 有週期）以前會被整個放棄 —— 那是最常見的情況，現在兩軸各自判斷，不重複的那軸取整個影像高度／寬度 |
#| **KLARF variant D 誤判**（M5 修正） | 真實 1.8 檔（ImageList 欄不在最後、且無 IMAGECOUNT 欄）被 `lint()` 判定每一列都違法，Export 精靈跳紅字 | `row_len_ok` 改用 `effective_row_len()`：把 `Images N { … }` 子區塊折算成一欄。**注意 `image_layout()` 對這個變體仍回 None，而 export 的插欄位置正好因此落在最後 —— 那是對的，別「順手修好」它**。迴歸測試 `tests/test_klarf_variant_d.py` |
#| **一張卡偷偷寫了第二條流**（F7-18 已改） | 畫布上那張 Denoise 畫在 test 那條鏈上，它其實同時改了 ref；而「要不要一起做」藏在控制列的 `also_apply` 勾選框裡，於是 test 是主角、ref 是附帶 | **一張卡一條流**：`resolve_writes` 只回主流。要對 ref 做就再放一張卡接到 ref。需要借另一條流的資訊時給它自己的 `image_key` 參數（`percentile_norm.range_from`），那條線在畫布上看得見。舊 recipe 的 `also_apply` 由 `recipe._migrate_also_apply` 展開成多張卡 |
#| **拆卡片時的順序陷阱**（F7-18） | `anchor="source"` 拆成兩張卡之後，如果 test 那張先跑，ref 借到的是「已經拉成 0–255」的範圍 —— 數字不一樣，而兩張輸出都是看起來正常的圖 | 借範圍的那幾張要排在**前面**。這類遷移不要讀程式碼驗證：跑同一份 recipe 100 顆，比 `min/median/max` 與 bin 數量是否逐項相同（`tests/test_ui_f7_18_streams_as_nodes.py`）|
#| **兩個節點之間只拉得動一條線**（F7-18 已修） | 先從 test 拉、再從 ref 拉，第二條只得到一句 `already connected` 然後什麼都沒發生 —— 使用者的結論是「這張卡不准我碰 ref」 | `edge_added` 帶第三個參數（**這條線從哪個輸出埠出發**），Studio 據此把下游卡的主要輸入指到那條流。同一對節點再拉一條要當成「我改變主意了」處理 |
#| **常駐在節點旁邊的裝飾**（F7-18 已清） | 每個輸出埠一顆「+」，十張卡的 pipeline 就有十幾顆加號跟資料流搶畫面 | 入口收回卡片庫；「+」做對的事（接上線、接在對的流上）改由「選著一張卡時從卡片庫加」承接（`add_card_after`）。加完**選取新卡**，連按三張才會長成一條鏈而不是倒過來 |
#| **虛線只是實線淡一點** | 「這條是我拉的」與「這條是排列順序帶來的」看起來只差深淺，而深淺會被縮放與主題影響 | 不同語意給不同**色相**（`canvas_edge_implicit`）。測試要鎖兩層：token 的色相差得出來，而且 `paint()` 真的去讀了它（畫進 pixmap 比主色相）|
#
#---
#
### 8. 待廠內驗證的假設（重要）
#
#開發全程用合成資料（真實資料不能出廠）。以下假設**必須在廠內用 `fab_probe/` 探測腳本確認**。
#那三支腳本是 stdlib-only 單檔、輸出純文字且預設遮蔽 Lot/Wafer/Device 等識別碼，
#設計成可以直接複製貼出廠區（細節與資料外流說明見 `fab_probe/README.md`）：
#
#| 假設 | 現況 | 用哪支腳本確認 |
#|---|---|---|
#| 1. EBI patch 的 page→channel 對應 | 假設每顆 defect 第一張=test、第二張=ref（`load_dataset` 的 `channel_order`） | `probe_tiff.py FILE.tif --with-klarf FILE.klarf` → 看它回報的配對型態（pairs / single / triples）。`probe_stats.py` 的奇偶頁均值比較可佐證 |
#| 2. `nm_per_px` 來源 | 找不到，暫為 None（CD 量測的 nm 值因此是 0） | `probe_klarf.py` 的 nm_per_px 名稱搜尋段；`probe_tiff.py` 的解析度/描述標籤 |
#| 3. KLARF 變體 | `klarf_core` 已知四種（含 M5 修正的 variant D） | `probe_klarf.py` 的 image-layout 變體判定與證據 |
#
#**每遇到一種新變體 → 做成最小化合成 fixture → 永久回歸測試**（見
#`tests/test_klarf_variant_d.py` 的寫法：先斷言「這份檔案確實是該變體」當前提，再測行為）。
#
### 9. 進度與下一步
#
#| Milestone | 狀態 | 內容 |
#|---|---|---|
#| M0 抽庫 | ✅ | 從 KLIP/GLAS/MMH/PEAR/CPE/Fusi³ vendoring 演算法資產 |
#| M1 引擎 | ✅ | Context/Step/Recipe DAG/表達式/14 張卡/合成資料/CLI |
#| M2 批次 | ✅ | ProcessPool + 影像段快取 + SQLite 歷史 + rescore |
#| M3 Studio | ✅ | PySide6 四區塊視覺化編輯器 |
#| M4 雙輸入 | ✅ | RSEM 單張 ingest、輸入型別分流、Golden Cell + Cell 週期估測卡（`period.choose_origin` 相位搜尋已補完）。驗收達成：`examples/recipes/dual_route_basic.json` 同時吃 EBI patch 與 RSEM，跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1% |
#| M5 Gallery+Export | ✅ | Gallery（虛擬捲動、排序、直方圖點 bar 篩選）；KLARF 三種寫回模式（就地無損／另存含 ADCSCORE+ADCCLASS／Top-N）+ 寫回前預覽變更；CSV/Excel 報表（含抓漏率/誤殺率）；overlay；`fab_probe/` 三支探測腳本；CLI `adept export` |
#| M6 推廣包 | ✅ | 離線安裝三件套（`tools/fetch_wheels.py` / `install_offline.py` / `doctor.py`，全 stdlib-only）、首啟導覽 + 範例 recipe 庫對話框、5 份範例 recipe。快速參考卡 PDF 暫緩（移到 backlog） |
#| M7 UI/UX | ✅ | A 組防呆 + **UI 全英文**（`tests/test_ui_english_only.py` 鎖住）。F7 全數完成：patch-only 收斂（`ui/scope.py`）、中性色/平面主題 + 暗色、卡片依流程階段分組 + 搜尋 + 前置條件 badge、**Region 段（具名 ROI）**、Results 視窗、**節點畫布**。計畫書 `docs/plans/F7-canvas-and-taxonomy.md` |
#| F7-18 | ✅ | **影像流是節點的事，不是控制列的事**（試用回饋第五輪）：拿掉輸出埠上常駐的「+」（入口收回卡片庫，接線與影像流由 `add_card_after` 承接）、**虛線給自己的色相**（`canvas_edge_implicit`；同色淡一點只說得出「比較不重要」）、**一張卡一條流**（七張 Enhance 卡的 `also_apply` / `anchor` 拿掉；`percentile_norm` / `glv_mask_norm` 補 `range_from` 保住「兩張圖還比得起來」）、**連線指定影像流**（`edge_added` 帶出發埠；同一對節點再拉一條是「我改變主意了」）。舊 recipe 由 `recipe._migrate_also_apply` 展開成多張卡，分數逐項相同。計畫書 §22 |
#| F7-17 | ✅ | **右下角變成「這張卡自己的儀表」**（依 `Step.key` 註冊，沒註冊的用原本的特徵表 → 加新卡不必動 UI）。四個：`load_patch` 的 **page→stream 對應**（廠內假設 #1 第一次看得見）、Enhance 九張卡的 **before/after 直方圖 + 削平計數**（新增 `Context.track_changes`，**只有預覽打開**）、`align` 的**整批位移散佈圖 + 搜尋半徑框**、五張量測卡的**整批分布 + 這一顆站在哪**。第二批：`roi_profile` 的曲線面板**收進同一個機制**（原本是平行的另一條路）、`roi_template` 的**三道閘門各自的門檻線**（match / certainty / **structure** 三種失敗的處置完全不同）。計畫書 §21 |
#| F7-16 | ✅ | **四張安全網**：**復原/重做**（存整份快照，不是反向操作；滑桿一次拖曳算一步）、**快捷鍵**（Ctrl+O/S/R/Z/0/±/F/←→，全照 OS 慣例，並寫進 tooltip）、**關窗前問「還沒存」**（存檔失敗不算可以關）、**跑到一半可以停**（引擎本來就支援，只是按不到；已跑完的留著，而且訊息講「stopped」不是「finished」）。計畫書 §20 |
#| F7-15 | ✅ | **畫面上的字要能被讀完**（C 組）：參數說明**收成一行、用到才攤開**（錯誤永遠攤開；`hint_text()` 回全文）、沒資料時最大的那一塊給「Open KLARF… / Try it with sample data」、**狀態列的拒絕變紅字**（`_status(msg, "error")` + QSS，逐條列舉哪些算 error）。計畫書 §19 |
#| F7-14 | ✅ | **從畫布上就做得完一條 pipeline**（B 組）：輸出埠上的 **「+」**（清單只列**現在就接得上**的卡，依階段排序；按哪個埠決定新卡做在哪條流上；接出來的是實線）、**畫布縮放控制**（左下四顆 + 百分比，夾在 25–300%）、**節點副標印 `吃什麼 → 吐什麼`**（Region 卡取 `resolve_regions_out`；重複的卡才帶 id）。計畫書 §18 |
#| F7-13 | ✅ | **控制項要看得出自己是什麼**（試用回饋第四輪 A 組）：下拉選單的箭頭（0 個畫素的 QSS 坑）、`template` 參數型別（按鈕 + 摘要，不是文字框，入口從預覽面板搬回參數列）、`Step.configuration_issues()` → lint `not-configured` → **畫布上的警示標記**、工具列按鈕看起來像按鈕。計畫書 §17。**未做**：n8n 的輸出埠 `+`、畫布縮放控制、節點副標印關鍵參數 |
#| F7-12 | ✅ | **ROI 定位第二批：Golden Cell 模板**。匯入一張原大圖 → 量週期 → 疊出一個完整 cell 當模板 → 在 cell 上標一次框，每顆 patch 用 NCC 對回相位再把框搬過來。patch **小於**一個週期沒關係（是把小 patch 滑進大模板，不是兩張小圖互相對位）。模板凍進 recipe（base64 純文字，不是路徑）。新卡 `roi_template` + `ui/template_dialog.py`。三道閘門見 §7 表。計畫書 §16。**未做**：用當次的大圖對凍住的 GC 做健檢 |
#| F7-11 | ✅ | **ROI 定位第一批**：量測卡 `output_prefix`（多區域的前置；Studio 挑了區域自動填名）、**投影定位卡** `roi_profile`（壓成曲線→找轉折→挑一段，可一次吐出鄰段）、**曲線面板**、**區域跨顆檢視**（把框畫到前 N 顆縮圖上，可只看定位失敗的）。定不出來就退回整張圖並標 `locate_ok=0`。順手修掉「過期的背景預覽會蓋掉新畫面」。計畫書 §15 |
#| F7-10 | ✅ | **route 的隱含順序畫成虛線**（畫布上「沒有線」以前不代表「沒有連接」，而使用者看到的是九張互不相干的卡）；**Enhance 補齊空間性 artifact**：新卡 `flatten`（背景梯度／掃描線條紋／top-hat／black-hat 五個方法一張卡）與 `local_contrast`（CLAHE），邊緣保留去噪塞進既有 `denoise`、雙流運算塞進既有 `subtract`。計畫書 §14 |
#| F7-9 | ✅ | 試用回饋第三輪：**六個階段六個顏色**（`theme.group_hex`，ΔE ≥ 25 且明度差 ≤ 15，兩條都有測試鎖）、**埠座標系 bug**（殘影＋「後面沒有圓框」同一個因）、**開窗就有 Input 起手卡**、**`image_keys` 參數型別**（`also_apply` 從自由文字變成勾選框）+ `ParamSpec.label`、**點卡片不再跳到 ref**、**具名 ROI 納入 lint** + Studio 試跑前先 lint。計畫書 §13 |
#| F7-7 / F7-8 | ✅ | 試用回饋兩輪：階段大按鈕 → **直式 icon rail**（卡片區收起來時整欄只剩 rail）、載入/試跑進度條、Brightness/Contrast + **Gamma / Curve** 卡、**每個有上下界的參數配滑桿**、**自訂色調曲線**（保單調插值）、**並排比對兩條影像流**（連動縮放平移）、畫布 n8n 化（圖示磚／點陣底／方向箭頭／每條影像流一條線）。詳見計畫書 §12 |
#
#v2 backlog：快速參考卡 PDF、自由 DAG 畫布、ground-truth 標注 + 混淆矩陣、ML Classify 卡
#（吃現成的 feature vector CSV）、PCA Ref、Region Stats/FFT、BSE/SE 多通道融合。
#
#---
#
### 11. 產品範圍開關（F7-1）
#
#**Studio 目前只吃 EBI patch。** RSEM 的能力（ingest、Golden Cell、週期估測、
#範例 recipe、測試）**完全沒有被刪**，只是從 GUI 上收起來。
#
#要打開，改 `adept/ui/scope.py` 一個常數：
#
#```python
#SUPPORTED_KINDS = ("ebi_patch",)            # 加 "rsem" 就整條路線回來
#HIDDEN_STEPS = ("golden_cell", "cell_period")   # 清空就出現在卡片庫
#```
#
#`tests/test_ui_patch_only.py` 同時鎖住兩邊：GUI 真的收斂了，而且
#**打開開關就回得來**（那支測試會 monkeypatch 這兩個常數再驗一次）。
#
#> ⚠ **`adept/core/algo/period.py` 不要刪。** 它現在只被 Golden Cell 用到，
#> 看起來像是可以跟 RSEM 一起砍掉的東西 —— 但 `estimate_period` /
#> `choose_origin` 的相位搜尋是之後做 **pattern-frame ROI** 的唯一工具
#> （patch 是以 defect 為中心裁切的，晶格相位逐顆不同；
#> 見 `docs/plans/F7-canvas-and-taxonomy.md` §4）。
#
#CLI 不受影響：`python -m adept run` 照樣跑得動 rsem recipe。
#
#---
#
### 9.5 部署到受限的廠內機器
#
#**完整的環境限制看 [`AGENTS.md`](AGENTS.md)** —— 開發在家用機（有 git、能下載、
#但**沒有真實資料**），執行在公司機（**只有那裡有資料**，但不能裝 git、
#目前什麼都下載不了）。唯一的傳輸通道是**在 GitHub 上看到檔案並按複製鈕**。
#
#三條路，用在不同時機：
#
#| 情況 | 用什麼 |
#|---|---|
#| 第一次搬整包 | `bundle/ADEPT_part1of6.py` … `part6of6.py`，每一批貼進去跑一次（分批是因為 **GitHub 不顯示超過 1 MB 的檔案**）|
#| 之後更新 | 複製 `tools/FILELIST.txt`（12 KB）→ `python tools/check_files.py` → 它列出要重新複製哪幾個 |
#| 只想跑格式探測 | 直接複製 `fab_probe/probe_*.py`（stdlib-only 單檔，**不需要整個 repo**）|
#
#網路哪天通了還有 `tools/get_code.py` / `.ps1`（逐檔抓）。其餘對應設計：
#
#- 整個 repo **只有純文字檔**（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml` + 一份 `.klarf`），
#  所以 GitHub「Download ZIP」下載得下來（那份 zip 不含 `.git`；170 個檔案、約 830 KB）。
#  **不要把 `.git` 打包給使用者** —— 二進位 pack 物件 + `hooks/*.sample` 腳本會觸發 DLP。
#- **「純文字」是必要條件，不是充分條件。** DLP 也掃**內容**，而最容易破功的地方是
#  測試 fixture：一份真實的 KLARF 帶著 Lot／Wafer／機台／device／**recipe 名稱**
#  （通常編碼了層別與製程步驟）、缺陷分類名稱，甚至廠區代號 —— 而那些值對測試
#  完全沒有用（`test_klarf_variant_d.py` 斷言的全是結構）。已全部遮蔽，
#  並由 `tests/test_no_real_fab_data.py` 守著（白名單 + 合成命名規則，
#  **不是列出不准出現的字** —— 那等於把要保護的東西寫進 repo）。
#- Download ZIP 是從 **`codeload.github.com`** 出來的，不是 `github.com`。
#  「以前下載得到、現在被擋」最常見的原因是 proxy allowlist 只放了後者，
#  跟 repo 內容無關。分辨方式與替代路徑見 `docs/NO-GIT-SETUP.md`。
#- **連 zip 都下載不了**（實際遇到：proxy 只放行 `github.com`，沒放 `codeload`）→
#  `tools/get_code.py`：只用 `raw.githubusercontent.com` **一台主機**逐檔抓，
#  每個檔案對 `tools/FILELIST.txt` 的 git blob SHA 驗過才落地。
#  驗 SHA 不是龜毛：被擋的 proxy 常常回一頁 HTML 而且是 **HTTP 200**，
#  那種東西寫進 `.py` 之後症狀是「程式碼都在但 import 就語法錯誤」。
#  清單由 `tools/make_filelist.py` 產生，有測試擋它腐爛（見 §6）。
#- 相依套件走離線 wheels：`tools/fetch_wheels.py`（有網路的機器）→ 帶 `wheels\` 過去 →
#  `tools/install_offline.py`（廠內機器）。全部 stdlib-only，因為它們在套件裝好之前就要能跑。
#- 裝不起來或跑不動時的第一件事：`python tools/doctor.py` —— 逐項 ✓/✗ 並附「怎麼修」。
#  最常見的失敗是 **wheels 的 Python 版本與機器上的不符**（cp39 的輪子配 py3.12），
#  `install_offline.py` 會在 pip 之前就攔下來並講清楚。
#- 詳細步驟：`docs/OFFLINE-INSTALL.md`；不用 git 的取得方式：`docs/NO-GIT-SETUP.md`。
#
#---
#
### 10. 來源專案對照（vendoring）
#
#每個 vendored 模組檔頭都註明來源與改動。原始專案：
#
#| 來源 | 提供了什麼 |
#|---|---|
#| **KLIP** | KLARF 1.2/1.8 無損引擎、TIFF page 對應、健檢 lint |
#| **GLAS** | fine align、SEM loader、DAG 拓撲排序概念、ROI label map 契約 |
#| **MMH** | recipe 架構原型、批次引擎模式、次像素邊緣定位、品質指標、KLARF 寫回 |
#| **PEAR** | GLV 統計 metric bank、Tukey 離群、η²/Cohen's d、CJK-safe 影像載入 |
#| **cell-period-estimator** | 週期估測、Golden Cell 堆疊、ghosting 分數 |
#| **Perspective-Combination (Fusi³)** | 正規化、直方圖匹配、5-backend 對位、SNR map、blob 分割、MultiROISet |
#
#F 0e34f6c1f9b0afc82d5ffc4b5bba0533aa14a97e 174 README.md
## ADEPT — Auto Defect Evaluation Pipeline Tool
#
#> 彈性、多步驟、**任何 Inspection 站點都適用**的 ADC（Auto Defect Classification）工具。
#>
#> 讀半導體 E-beam Inspection 的 patch 影像（test + ref）或 Review SEM 單張影像 +
#> 對應的 KLARF，用「步驟卡片組 pipeline」把腦中的想法變成算法，對每顆 defect 算分、
#> 調參看整批分佈、再把結果寫回 KLARF。
#>
#> **核心理念：站點差異封裝進 recipe，不封裝進程式碼。**
#> 傳統 PADC / RADC 每個站點都要工程師重寫一份 code；ADEPT 讓不會寫 code 的人
#> 也能用滑鼠把想法組成算法，產出可量化的證據。
#
#| | |
#|---|---|
#| **輸入** | KLARF + multi-page patch TIFF（EBI）｜KLARF + per-defect 影像（Review SEM）｜純資料夾 |
#| **組裝** | 19 張步驟卡片，三段式：影像（把圖變乾淨）→ 算法（量出數字）→ ADC 判定（算分分 bin） |
#| **輸出** | 無損寫回 KLARF（class / bin / DSIZE）｜Top-N 新 KLARF｜CSV / Excel 報表｜feature vector（ML 備料） |
#| **介面** | PySide6 Studio 視覺化編輯器 ＋ CLI（可排程、可腳本化） |
#
#完整計畫見 [`docs/plans/F0-master-plan.md`](docs/plans/F0-master-plan.md)；
#接手開發請先讀 **[`docs/HANDOVER.md`](docs/HANDOVER.md)**（由來、決策理由、來源專案脈絡、
#哪些已驗證哪些還是假設）與 [`CLAUDE.md`](CLAUDE.md)（操作手冊）。
#
### 目前進度：M0–M6 全部完成 ✅（v1 功能齊備）
#
#M0：六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator / Perspective-Combination）
#的可重用演算法已 vendoring 進 `adept/core`，全部通過合成影像單元測試、零 Qt 依賴。
#
#M1：pipeline 引擎完成 —— Context/Step 契約、Recipe(DAG) + lint 驗證、score 表達式引擎
#（安全語意，不會爆給使用者看）、單顆執行引擎、14 張卡片、合成資料產生器、CLI。
#端到端驗收：合成 lot（24 顆、真/假各半）上範例 recipe 分類正確率 ~94%（跨 seed）。
#
#M2：ProcessPool 平行批次（單顆爆不殺整批、progress/abort）、**影像段 checkpoint 快取**
#（改算法段參數/門檻只重算後半）、SQLite 批次歷史 + **rescore**（改表達式/門檻不重跑影像）、
#feature vector CSV 匯出。實測（2 核容器、2000 顆合成 patch）：cold 17.5 ms/顆 →
#warm cache 2.2 ms/顆 → rescore 0.17 s；換算 8 核廠內機 10k patch 約 1 分鐘、rescore 秒回。
#快取空間約 50 KB/顆（10k ≈ 500 MB，可隨時清）。
#
#M3：**Studio 視覺化介面**（PySide6）—— 卡片庫｜Pipeline｜單顆預覽｜分數直方圖 四區塊，
#三段式分色（影像藍／算法橙／ADC 判定紫）。點卡片看該步驟的中間輸出、參數表單自動由
#ParamSpec 生成（每格都有白話說明、範圍防呆、錯誤即時紅字）、拖門檻線即時看 bin 數變化。
#**全程滑鼠，不用寫一行 code。**
#
#M4：**雙輸入** —— Review SEM 單張影像（KLARF + 每顆一張圖）與 EBI patch（test/ref 配對）
#都能吃，ingest 自動判別型別、recipe 自動走對應 route。沒有 ref 影像時由新的
#**Golden Cell 卡**把圖上重複的 cell 疊成一張乾淨參考圖（含晶格相位自動搜尋）。
#驗收：`examples/recipes/dual_route_basic.json` 一份 recipe、一個門檻，跨 3 seeds ×
#2 種輸入共 144 顆合成 defect，分類正確率 95.1%。
#
#M5：**Gallery + 輸出**。Gallery 把整批 defect 以縮圖網格攤開（虛擬捲動，10k 顆不卡），
#可按分數或任一特徵排序，**點直方圖的長條就篩出那個分數區間的 defect** —— 調參迴圈
#從一顆一顆點，變成一屏一屏掃。輸出精靈支援三種 KLARF 寫回（就地改欄無損／另存含
#ADCSCORE+ADCCLASS 欄／Top-N 篩選新檔），**寫回前一定先預覽會改什麼**；另有 CSV /
#Excel 報表（給 ground truth 就算抓漏率、誤殺率、混淆矩陣）與 overlay 影像。
#另附 `fab_probe/` 三支 stdlib-only 探測腳本，用來在廠內確認格式假設（見下）。
#
#M6：**推廣包**。離線安裝三件套（`fetch_wheels` → `install_offline` → `doctor`，
#全部 stdlib-only，因為它們得在套件裝好之前就能跑）讓 pip 連不出去的廠內機器也裝得起來；
#Studio 首次開啟有導覽，按一下「用範例資料試一次」就會自己產生合成資料、載入範本、
#跑完一批，直接看到有分數的直方圖與 Gallery；範例 recipe 庫有 5 份，
#每一份示範一種不同的作法（見 `examples/recipes/README.md`）。
#
#```bash
## 開 Studio：
#python -m adept gui
#
## CLI 試玩（不需真實資料）：
#python tools/make_sample.py /tmp/lot --n 100         # 產合成 KLARF + patch TIFF
#python -m adept steps                              # 看所有卡片
#python -m adept validate examples/recipes/die_to_die_basic.json
#python -m adept run examples/recipes/die_to_die_basic.json /tmp/lot/LOT_SYN.001 \
#    --workers 4 --cache /tmp/cache --db /tmp/runs.db --csv features.csv
#python -m adept runs --db /tmp/runs.db             # 批次歷史
#python -m adept rescore <run_id> --db /tmp/runs.db --threshold 60 --save   # 秒級調門檻
#python -m adept export <run_id> --db /tmp/runs.db --mode annotate \
#    --klarf-out out.001 --csv feat.csv --excel report.xlsx   # 寫回 KLARF + 報表
#```
#
#```
#adept/
#├── ui/                  # PySide6 Studio（唯一允許 Qt 的地方）
#│   ├── viewmodel.py     #   RecipeModel（Qt-free 編輯模型）+ 直方圖/門檻計算
#│   ├── theme.py         #   GLAS 暖色主題 token + 三段分色
#│   ├── widgets.py       #   ImageView / ParamForm / LibraryPanel / PipelinePanel
#│   │                    #   / HistogramWidget / FeatureTable / VerdictChip
#│   ├── workers.py       #   載入 / 預覽（請求合併）/ 試跑 背景執行緒
#│   ├── studio.py        #   StudioWindow 四區塊組裝
#│   └── app.py           #   進入點（python -m adept gui）
#├── core/
#│   ├── ingest/          # KLARF 無損引擎(KLIP) + TIFF page 索引 + Dataset 自動判別
#│   │   ├── klarf_core.py    #   KLARF 1.2/1.8 讀寫/健檢/比對 + defect↔page 對應
#│   │   ├── tiff_index.py    #   免解碼 TIFF/BigTIFF 盤點 + tifffile 讀 page
#│   │   ├── imageio.py       #   CJK-safe 影像讀寫
#│   │   └── dataset.py       #   ebi_patch / rsem / folder 自動判別 → DefectItem
#│   ├── algo/            # 純 numpy/cv2 演算法（未來 step 卡片包這些）
#│   │   ├── normalize.py     #   percentile / GLV-mask 正規化        (Fusi³)
#│   │   ├── histmatch.py     #   直方圖匹配 exact/linear/percentile  (Fusi³)
#│   │   ├── align.py         #   5-backend 對位 + robust + template  (Fusi³/GLAS)
#│   │   ├── snr.py           #   canonical SNR + ROI SNR + SNR map   (Fusi³/PEAR)
#│   │   ├── blob.py          #   defect blob 分割 + 幾何特徵          (Fusi³)
#│   │   ├── roi.py           #   正規化座標 MultiROISet               (Fusi³)
#│   │   ├── glv.py           #   GLV 統計 metric bank                 (PEAR)
#│   │   ├── stats.py         #   Tukey 離群 / Cohen's d / η²          (PEAR)
#│   │   ├── period.py        #   cell 週期估測                        (CPE)
#│   │   ├── golden.py        #   Golden Cell 堆疊 + ghosting 分數     (CPE)
#│   │   ├── quality.py       #   focus/品質三指標                     (MMH)
#│   │   └── subpixel.py      #   次像素邊緣定位（CD 用）              (MMH)
#│   └── calibration.py   # nm/px 校正 profile 管理                    (MMH)
#├── tests/               # 合成影像單元測試 + 零 Qt / py3.9 語法守門
#├── docs/plans/          # 開發計畫（F0 = master plan）
#├── (fab_probe/)         # 廠內格式探測腳本 —— 尚未建立，見 CLAUDE.md §8
#└── tools/               # (M1+) 合成資料產生器、CLI
#```
#
### 廠內格式驗證
#
#開發全程用合成資料，有三個假設必須用真實檔案確認（page→channel 對應、
#`nm_per_px` 來源、KLARF 變體）。`fab_probe/` 裡三支 stdlib-only 單檔腳本負責這件事，
#輸出是**純文字、預設遮蔽 Lot/Wafer/Device 識別碼**，設計成可以直接複製貼出廠區：
#
#```
#python fab_probe\probe_klarf.py C:\path\to\file.klarf > report.txt
#python fab_probe\probe_tiff.py  C:\path\to\file.tif --with-klarf C:\path\to\file.klarf
#python fab_probe\probe_stats.py C:\path\to\file.tif
#```
#
#資料外流說明與逐項用途見 [`fab_probe/README.md`](fab_probe/README.md)。
#
### 沒有 git 的機器？
#
#整個 repo 只有純文字檔（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml`），
#不需要 git 也能用：GitHub → **Code** → **Download ZIP** → 解壓 → `pip install -r requirements.txt` → 跑。
#完整步驟（含公司擋 pip 時的離線 wheels 作法）見 **[`docs/NO-GIT-SETUP.md`](docs/NO-GIT-SETUP.md)**。
#
### 開發環境
#
#```bash
#python -m venv .venv && .venv\Scripts\activate     # Windows
#pip install -r requirements.txt   # 含 PySide6（Studio 用）
#pip install pytest
#QT_QPA_PLATFORM=offscreen pytest -q   # 全部測試（~6s，不需真實資料；Windows 免設 QT_QPA_PLATFORM）
#```
#
### Vendoring 慣例
#
#- 每個 vendored 模組檔頭註明來源專案/檔案與改動清單。
#- `adept/core` 禁止 Qt import（`tests/test_no_qt.py` 守門）。
#- Python ≥ 3.9 相容（同樣由測試以 `ast.parse(feature_version=(3,9))` 守門）。
#
### 統一慣例（M0 修正的三個歷史摩擦）
#
#1. **ROI 座標**：正規化座標（`NamedROI`）為正典；像素矩形一律 `(x, y, w, h)` tuple。
#2. **SNR 正負號**：`snr_signed = (μ_target − μ_ref) / σ_ref`（e-beam 定義，PEAR 版）
#   為唯一正典 primitive（`algo/snr.py`）；`roi_snr` 同時回報 signed 與 abs。
#3. **`compute_snr_map`** 改回傳 `SnrMapResult(map_float, snr_max)`（原 Fusi³ 版
#   回傳 tuple 與型別註記不符）。
#
#另：vendoring 過程發現並修正原 Fusi³ `ecc` 對位 backend 的位移正負號 bug
#（與其他四個 backend 相反），已在 `algo/align.py` 檔頭記錄。
#
### Roadmap
#
#M0 抽庫 ✅ → M1 引擎 ✅ → M2 批次 ✅ → M3 Studio UI ✅ → M4 雙輸入+Golden Cell ✅ →
#M5 Gallery+Export ✅ → M6 推廣包 ✅。詳見 master plan。
#
### 已知修正紀錄（開發過程中抓到的坑）
#
#- **Fusi³ `ecc` 對位 backend 位移正負號**與其他四個 backend 相反 → 已修（`algo/align.py`）。
#- **OpenCV IPP 非決定性**：同張圖算兩次會有 ~1e-8 差異（SIMD 路徑依緩衝區位址而變），
#  導致快取結果無法 bit-identical → `batch.pin_cv2_deterministic()` 關閉 IPP。
#- **fork 死鎖**：Linux 預設 fork 若從非主執行緒（GUI 的 QThread）呼叫，
#  ProcessPool 100% 卡死 → `batch._pool_context()` 改為主執行緒 fork、非主執行緒 spawn
#  （迴歸測試 `tests/test_batch_thread_safety.py`）。
#
#F 2a8f038b82940602ac42b1724959afe84d9ae30d 1457 SESSION_LOG.md
## SESSION_LOG
#
#開發歷程。**每次 session 結束請在最上方新增一段。**
#
#---
#
### 兩台機器：把環境限制寫下來，並照它重做搬運（2026-07-30）
#
#使用者把實際的開發限制講清楚了，而那些限制**解釋了前面幾輪為什麼一直在撞牆**：
#
#| | 家用機（開發） | 公司機（執行） |
#|---|---|---|
#| git | ✅ | ❌ |
#| 下載 | ✅ | ❌ **目前什麼都下載不了**（.zip、.py 都擋）|
#| 看得到 GitHub + 複製鈕 | ✅ | ✅ |
#| 執行 `.py` | ✅ | ✅ |
#| `pip install` | ✅ | ✅（走**內部 PyPI 鏡像**，不是 proxy）|
#| **真實資料** | ❌ | ✅ **只有這裡有** |
#
#最後一列是整個專案的形狀來源：**開發的地方沒有資料，有資料的地方不能開發。**
#所以合成資料產生器不是玩具、`fab_probe` 不是附屬品，它們是唯一的驗證路徑。
#
#### 傳輸通道是剪貼簿 —— 而它有一個我沒想到的硬限制
#
#使用者自己找到的作法（貼文字內容、另存 `.py`、執行）是對的。但
#**GitHub 不顯示超過 1 MB 的檔案** —— 那包 2.3 MB 在公司機上根本點不開來複製。
#「打包成功但送不進去」是最糟的一種「做完了」。
#
#所以 `make_text_bundle.py` 加 `--split`：六批，每批 < 420 KB。三個設計決定：
#
#- **每一批都是獨立可執行的**，不需要合併、順序不重要、重複執行沒關係。
#  合併文字檔的話，一次貼歪就要重來，而且看不出是哪一批壞的。
#- **`tools/FILELIST.txt` 固定放第一批**，後面每一批解完都用它回報「還缺幾個」。
#- **只貼一批的時候絕對不能印「下一步：跑 doctor」**。第一版就是這樣 ——
#  少了一百多個檔案卻長得像整包到位了。這是這一整輪反覆在防的同一件事。
#
#### 更新不該重跑整套搬運
#
#`tools/check_files.py`：複製 `tools/FILELIST.txt`（12 KB）→ 它列出**哪幾個檔案要
#重新複製**（缺少的／內容不一樣的，`--urls` 連 GitHub 網址一起給）。
#所以更新一次是「一次小複製 + 幾次針對性複製」，不是六批重搬。
#
#而且要驗證 `CLAUDE.md` §8 那三個廠內假設**根本不需要整個專案** ——
#`fab_probe/probe_*.py` 各 24–46 KB、stdlib-only、單檔，複製過去就能跑。
#這一條前面幾輪都沒講，而它是最省力的一條。
#
#### `bundle/` 進 repo 的取捨
#
#產出物進版控通常是壞味道，但公司機**唯一**的取得管道就是「看得到 GitHub」——
#所以那六批必須在 repo 裡才拿得到。兩件事因此必須做：
#
#- `bundle/` 從 `FILELIST.txt` 與打包來源**排除**。不排除的話 `get_code.py` 會白抓
#  2.4 MB，而分批解包的「還缺幾個」永遠到不了 0（那些檔案本來就不在包裡）。
#- 重打包**刻意不自動化**。每次 commit 都重產六個 400 KB 的檔案會讓 diff 變成噪音，
#  所以那是「要搬進公司機之前」才做的動作，寫在 `CLAUDE.md` §6 與 `AGENTS.md` §4。
#
#### 文件
#
#新增 **`AGENTS.md`**（環境與限制），`CLAUDE.md` 開頭改成三份文件的分工：
#`AGENTS.md` 講環境、`HANDOVER.md` 講為什麼長成這樣、`CLAUDE.md` 講怎麼動手。
#`docs/NO-GIT-SETUP.md` 整份重排 —— 它原本第一句就叫人按「Download ZIP」，
#而那正是不能用的東西；現在開頭是一張「你的機器下載得了東西嗎」的分流表。
#
#`AGENTS.md` 裡有一節專講**哪些程式碼形狀是這些限制的直接後果**
#（stdlib-only、Python 3.9、純文字、`FILELIST.txt`、驗 SHA、鐵則 8）——
#因為那些東西單獨看都像過度設計，而下一個人會「順手簡化」掉它們。
#有一支測試要求這些限制寫在 `AGENTS.md` 裡且 `CLAUDE.md` 指得到它。
#
#---
#
### 連 .zip 這個類別都被擋 → 單檔純文字包（2026-07-30）
#
#使用者要我把整包壓成 zip 傳給他當測試。結果：**一樣被擋**。
#
#### 這個測試推翻了我前面的結論
#
#我一直說「請 IT 放行 `codeload.github.com`」是根治。**不是** —— 那樣拿到的還是
#一個 zip，而政策擋的是 `.zip` 這個類別（從別的來源下載同一包也擋）。
#所以那條 request 從「根治」降級成「順便也該修」。
#
#而 `get_code.py` / `.ps1` 抓的是 `text/plain`（沒有壓縮檔），方向是對的 ——
#只是還卡在 proxy 那一關。能確定過得去的只剩「一個純文字檔」。
#
#### `tools/make_text_bundle.py`
#
#整個 repo 打成**一個 `.py`**：沒有壓縮、**也刻意不用 base64**（base64 對 DLP 來說
#是「看不懂的東西」，而看不懂通常就等於擋掉；而且這個 repo 全是純文字，本來就
#不需要編碼）。每個檔案的內容一行一行原樣躺在裡面，記事本打開就讀得到。
#
#**格式用「行數」而不是「位元組數」**：這個檔案很可能在某個環節被把 LF 換成 CRLF，
#而用位元組數的話那一換會讓**第一個檔案之後的全部檔案**對不起來 ——
#看起來像整包壞掉，而真正的原因（換行符號）沒有人會想到。
#
#### 寫這支的過程踩到三個坑，全部是「產出來看起來很正常」那一類
#
#1. **資料區是裸文字 → Python 先編譯整個檔案 → SyntaxError。** 跑的時候才發現它
#   去解析某個 `.md` 裡的全形括號。修法是資料區每一行前面加一個 `#`。
#2. **樣板過度轉義。** 解包程式是用字串樣板產的，`"\\\\n"` 寫多了一層，
#   產出的檔案裡是**字面上的反斜線加 n**，不是換行。產出來的東西長得完全正常，
#   直到去跑它。
#3. **分隔行在檔案裡出現三次**（解包程式的賦值、真正的分隔行、以及資料區 ——
#   `make_text_bundle.py` 自己也在 repo 裡）。所以 `split` 與 `rsplit` 都不對，
#   要找**整行剛好等於**它的那一行。而第 1 點的那個 `#` 剛好也解決了這件事：
#   資料裡的那一行永遠不會剛好相等。
#
#三個坑的共同點：**產出物看起來沒問題，錯誤發生在收到的人手上。** 所以測試是
#「打包 → 解開 → 跟 repo 逐位元組比對」，另外三支分別鎖住「產出的是合法 Python」、
#「換過行尾還解得開」、「內容被動過就一個檔案都不落地」，還有一支要求
#**打包前就拒絕**裝不進這個格式的東西（CRLF / 非 UTF-8）——
#拒絕產出比產出一個解不開的包好。
#
#### 順帶：打包這件事本身抓到一個資料外洩
#
#壓成 zip 之後掃了一遍內容，發現 `tests/test_no_real_fab_data.py` 裡有**真實的
#lot 與機台代號** —— 是我寫的，當成「證明這個守門測試擋得下真實值」的負面案例。
#而那個檔案自己的說明就寫著「不能靠列出不准出現的字來檢查」。已換成憑空編的字。
#
#**那個掃描本來就該在推上去之前做，而不是等到有人要我打包。**
#
#---
#
### zip 被擋 → 只用一台主機的取代路徑（2026-07-30）
#
#上一段列了三個可能的原因並給了分辨測試。使用者測完回報：**「開 codeload 會被擋」**
#—— 所以是**主機層封鎖**，不是 DLP 掃內容。
#
#### 這個答案決定了三件事
#
#1. **`.tar.gz` 不用試** —— 它在同一台主機上（`codeload.github.com`），換副檔名沒用。
#   一開始我把它列成「省事的第一個選項」，那是錯的建議。
#2. **根治是 allowlist**：`codeload.github.com` 跟 `github.com` 是同一個信任範圍，
#   只是 GitHub 把 archive 下載放在另一個網域。`docs/NO-GIT-SETUP.md` 直接附上
#   給 IT 的說法（要有「已放行 github.com 但未放行 codeload」這個對比，
#   不然那個 request 看起來像在要一個新的外部網域）。
#3. **不等 IT 的路：`tools/get_code.py`** —— 只用 **`raw.githubusercontent.com`
#   一台主機**逐檔抓。「一台」是重點：zip 就是死在「allowlist 有 github.com、
#   沒有 codeload」，而 `api.github.com`（列檔案用）會是第三台要放行的主機。
#
#### 幾個想清楚才寫下去的決定
#
#**清單要放在 repo 裡。** raw 送得出單一檔案但列不出目錄。所以
#`tools/FILELIST.txt`（每行 git blob SHA + 路徑）+ `tools/make_filelist.py`。
#
#**驗 git blob SHA，不是驗大小。** 被擋的 proxy **常常回一頁登入頁而且 HTTP 200**。
#那種東西寫進 `.py` 之後，症狀是「程式碼看起來都在，但 import 就爆語法錯誤」——
#使用者完全不會歸因到下載。SHA 對不上就不落地，而且訊息會講「開頭是 `<`，
#看起來真的是 HTML」。
#
#**怎麼拿到這支腳本本身**（雞生蛋）：在 blob 頁按複製鈕、貼進記事本。
#那個複製是從**已經載入的網頁**複製，不會再連別的主機。所以這支必須短、必須
#stdlib-only，而且說明要寫在 `.md` 裡而不是全塞進 docstring。
#
#### 實際跑一次抓到三個自己的 bug
#
#紙上看起來都對，跑完才知道：
#
#1. **404 被講成「這台主機也被擋掉了」。** 404 是 `HTTPError` —— 伺服器**有回答**，
#   代表連線是通的，真正的原因是 `--ref` 打錯。照原本的訊息，使用者會拿著
#   一個假問題去找 IT。現在分三類：伺服器回答了（404 = ref 錯、403/407 = proxy 拒絕）、
#   連不上（才是被擋）、TLS 被攔截（用 `--cafile`，**不是**關掉驗證，有測試守著）。
#2. **清單自己沒被抓下來。** 它不在自己的清單裡（SHA 沒辦法自我包含），
#   所以抓下來那份 repo 少一個檔案，**而且看不出來少了什麼**。位元組就在手上。
#3. **兩支清單同步測試在抓下來那一份上是紅的** —— 它們 shell out 到 `git ls-files`，
#   而那份 tree 沒有 `.git`。那正是這個功能的目標使用者，給他兩條紅字等於告訴他
#   「你下載壞了」。改成 skip 並附理由。
#
#驗收方式：`--ref <commit sha>` 抓一份下來跟 repo `diff -r`，**一個位元組都不差**，
#而且那一份自己跑得起來（只 skip 掉那兩支需要 git 的）。順帶量到一件要寫進文件的事：
#`--ref` 給**分支名**時抓到的是 CDN 上那一版，剛推完可能拿到前一個 commit
#（清單與檔案來自同一份快照，所以 SHA 仍然全對、不會誤報，但你拿到的是稍舊的一份）。
#要完全可重現就給 commit SHA。
#
#### 第四個誤診：使用者跑起來之後回報 WinError 10060
#
#我把它寫成「這台主機也被擋掉了」。錯了 —— **10060 是逾時**，意思是封包直接送
#出去而沒有人回應。而使用者的**瀏覽器連得到 GitHub**，所以答案幾乎一定是：
#**這台機器要透過公司 proxy 才連得出去，而 Python 沒有走 proxy。**
#
#`urllib` 會讀 `HTTPS_PROXY` 與 Windows 登錄檔裡**手動設定**的 proxy，
#但**讀不到 PAC（自動設定指令碼）** —— 而公司幾乎都用 PAC。瀏覽器懂 PAC、
#Python 不懂，所以同一台機器上一個通一個不通，而錯誤訊息完全看不出來。
#
#照原本的訊息，使用者會拿著一個假問題去找 IT 要一個他其實已經有的東西。
#現在：`--proxy` 參數、開頭就印出「現在會用哪個 proxy」（「直接連」這句話本身
#就是診斷）、逾時而且沒在走 proxy 時**去登錄檔把 PAC 的網址讀出來講給他聽**
#（`winreg` 是 stdlib），並附上 `netsh winhttp show proxy` / `pip config list`
#這些找得到答案的指令。已經在走 proxy 卻還逾時的時候講的是另一句話 ——
#不能叫他再去找一次他已經填好的東西。
#
##### 而且不要只把診斷講出來，能自己解就自己解
#
#使用者照著查出來的是：`ProxyServer` 空的、**`AutoConfigURL` 有值** —— 就是 PAC。
#而 `pip config list` 給不出 proxy，因為公司的 pip 是走**內部 PyPI 鏡像**
#（`index-url` 指到內網），根本沒有 proxy 設定。我把 `pip config list` 列成找 proxy
#的方法之一，那是錯的建議；而且**那個輸出裡通常含帳號密碼**（使用者就這樣貼出來了）。
#文件已改成明確叫人不要用它找 proxy，並提醒貼之前要遮掉。
#
#原本的下一步是「用瀏覽器打開 PAC 檔，找 `PROXY 主機:埠`」。那對製程工程師不合理：
#PAC 檔通常有上百行條件判斷，而**「哪一行適用於這個網址」正是 PAC 要算的東西**。
#
#所以改成讓程式自己算：Windows 上沒有其他 proxy 設定時，借 PowerShell 問 .NET
#`GetSystemWebProxy().GetProxy(url)`（瀏覽器用的就是同一套設定），解出來就直接用，
#開頭那行 `Proxy :` 講清楚它是怎麼來的。`.NET` 在「不需要 proxy」時會回傳原網址，
#所以那種情況要當成「沒有 proxy」；非 Windows、沒有 powershell、逾時、回一句看不懂
#的話 —— 全部安靜回空字串。**診斷用的東西壞掉不可以自己變成失敗原因**，這條有測試鎖。
#
##### 第五個誤診，以及為什麼最後多了一支 PowerShell 版
#
#PAC 解出來了（`Proxy :` 那行有值），但接著拿到 **WinError 10061 拒絕連線**。
#我給的訊息是「它沒有回應，確認位址與埠是對的」—— 那等於沒有診斷。
#
#**拒絕連線不是逾時**：位址查得到、封包也到了，只是那個埠上沒有東西在聽。
#而原因就在解出來的那個網址上 —— 它**沒有埠**，所以 urllib 用了預設的 80，
#而公司 proxy 幾乎不在 80。現在會講出這件事、列出常見的埠、給出從 PAC 檔撈出
#`PROXY 主機:埠` 的指令。
#
#但更根本的一件事是：`urllib` 有三件在這種環境下做不到的事 ——
#讀 PAC 只拿得到**第一個** proxy（PAC 常常給多個候選讓客戶端依序 fallback）、
#不會對 proxy 做 **Windows 整合驗證**（NTLM / Kerberos）、TLS 版本跟著 Python。
#這三件 .NET 全部原生支援，**而 PowerShell 就是 .NET** ——
#也就是**瀏覽器連得到的東西，PowerShell 通常就連得到**。
#
#所以加了 `tools/get_code.ps1`：契約跟 py 版完全相同（同一份 `FILELIST.txt`、
#同樣驗 git blob SHA、同樣 atomic 寫入），差別只在網路那一層。兩支並存的風險是
#「使用者不知道該用哪一支」，所以文件裡是一張對照表 + 一句判準，而且有測試要求
#兩支都出現在文件裡。
#
#**這支是真的跑過的**（容器裡裝了 PowerShell 7.4）：173 個檔案抓完、SHA 全對、
#內容跟 repo 逐位元組相同。而且跑第一次就抓到一個 bug ——
#`Join-Path` 把**絕對路徑**接在目前目錄後面，做出 `<repo>/tmp/x` 這種東西，
#**而它建得起來**，於是檔案安靜地跑到錯的地方（那次真的寫進了 repo 裡）。
#「寫到別的地方去了」是使用者最不會想到要檢查的失敗。改用 `IsPathRooted` 判斷，
#並補了測試（`pwsh` 不在的機器上 skip，不是 fail）。
#
#這是同一個教訓的第四次：**連線層的錯誤不可以一律講「被擋掉了」。**
#伺服器回答了（404 = ref 錯、403/407 = proxy 拒絕）、連不上、逾時而沒走 proxy、
#逾時但有走 proxy、**拒絕連線（埠不對）**、TLS 被攔截 —— 六種，處置全都不一樣，
#每一種都有測試鎖著。
#
#### 順帶
#
#`CLAUDE.md` §6 記下清單的更新順序：**`git add` 之後**才跑 `make_filelist.py`
#（它讀的是 `git ls-files`）。寫這段的時候那個守門測試擋了我兩次 —— 忘了重跑的話，
#那個檔案會在「只能逐檔抓」的機器上**安靜地少掉**，而那台機器沒有別的取得方式。
#
#---
#
### 廠內識別碼遮蔽 + 「ZIP 被擋」的查明（2026-07-30）
#
#使用者回報：**「GitHub 下載 .zip 會被擋（公司 policy），之前不會。」**
#
#### 查出來的東西
#
#先確認 repo 本身沒變質：170 個檔案全部純文字（`.py` / `.md` / `.json` / `.toml` /
#`.txt` / `.yml` + 一份 `.klarf`）、zip 約 830 KB、沒有二進位、沒有長 base64、
#最近加的檔案全是 `.py` 與 `.md`。**§9.5 的結構性前提還成立。**
#
#但掃內容的時候發現一件更該處理的事：`tests/fixtures/sample_real.klarf`
#（專案裡唯一一份真實來源的 KLARF，variant D 就是它抓到的）帶著一整組
#**真實的廠內識別碼**：廠區代號、Lot、Wafer／ScribeID、檢測機台、device、
#**RecipeID**（recipe 名稱編碼了層別與製程步驟）、缺陷分類名稱、檢測日期。
#`tests/test_fab_probe.py` 的 `REAL_LOT` / `REAL_WAFER` / `REAL_DEVICE` 三個常數
#也是真值（其中 device 名稱帶製程節點）。這些東西**在一個公開 repo 裡**。
#
#這同時是兩件事：一個資料外洩，以及「只有這個 repo 的 zip 被擋」最合理的解釋 ——
#公司自己的 Lot／device 命名規則正是 DLP 自訂 fingerprint 最典型的內容，
#而 DLP 是雙向掃的，下載也掃。
#
#### 做了什麼
#
#全部等長遮蔽成合成值。**一條測試都沒壞**，因為那些值沒有任何測試在看它 ——
#`test_klarf_variant_d.py` 斷言的全是結構（版本、欄位佈局、ImageList 在第幾欄、
#round-trip 逐位元組相同）。也就是說真實值留在裡面是**純風險、零收益**。
#
#新增鐵則 8 與守門測試 `tests/test_no_real_fab_data.py`。它刻意**不是**「列出不准
#出現的字」—— 那等於把要保護的東西寫進 repo。改成白名單 + 一條「看得出是編出來的」
#命名規則，而且有一支測試證明這個白名單擋得下真實樣式的值（白名單式檢查最容易
#變成「什麼都通過」）。
#
#### 「之前不會」還有兩個與 repo 無關的可能，已寫進文件讓使用者自己分辨
#
#1. **Download ZIP 是從 `codeload.github.com` 出來的，不是 `github.com`。**
#   proxy allowlist 只放後者 → zip 被擋但網頁看得到。這是「以前可以現在不行」
#   最常見的原因，而且跟我們的 repo 完全無關。
#2. **政策層面禁止 .zip 這個類別**（下載任何無關 repo 的 zip 也會被擋）。
#
#`docs/NO-GIT-SETUP.md` 原本寫著「企業 DLP 掃描不會有問題」—— 那句話太滿了，
#改成一張三種原因的分辨表（每種各一個 30 秒的測試）加上替代路徑
#（`.tar.gz`、請 IT 放行 codeload、`raw.githubusercontent.com` 逐檔抓）。
#
#### 還沒做（需要使用者決定）
#
#遮蔽只影響**現在的檔案**。GitHub 的 zip 不含 `.git`，所以下載的人看不到歷史 ——
#但原本的值還在 git 歷史裡。要完全清掉需要**重寫歷史**（`git filter-repo`）或把
#repo 改成 private，兩者都會影響已經 clone 過的人，所以等使用者決定。
#
#919 tests。
#
#---
#
### F7-18 —— 影像流是節點的事，不是控制列的事（2026-07-30）
#
#使用者三件回饋。前兩件看起來是外觀（一顆按鈕、一個顏色），第三件才是主菜 ——
#但三件是同一句話的三個面：**畫布是主體，控制列是配角。**
#
#### 1. 那顆「+」我自己收回來
#
#F7-14 加它的理由沒有錯（「哪張卡接得上」引擎本來就知道，不該讓使用者自己判斷），
#但它**常駐**：每個輸出埠一顆，十張卡的 pipeline 就有十幾顆加號長在節點旁邊，
#而它們跟資料流無關。使用者的話是「會永久存在，還是手動從旁邊功能卡添加好了」。
#
#所以入口收回卡片庫 —— 但「+」做對的兩件事不能跟著丟掉。現在**選著一張卡的時候
#從卡片庫加，新卡就接在它後面、做在它那條流上**，而且加完會選取新卡，
#所以連按三張卡片長成的是一條鏈，順序就是按下去的順序（永遠插在同一張後面的話
#會倒過來，那是我第一版寫錯的地方）。
#
#`cards_addable_after()` 跟著走了：卡片庫本來就把 22 張全列出來並標 `needs diff`，
#留兩套「哪些卡現在能用」的邏輯並存必定腐爛。
#
#### 2. 虛線不能只是實線淡一點
#
#以前是 `canvas_edge` 加 alpha 120。同一個顏色淡一點只說得出「比較不重要」，
#但這兩種線在語意上是**不同的東西**：實線是使用者拉的、刪得掉；虛線是卡片排列
#帶來的順序、刪不掉，它的意思是「這裡**可以**拉一條」。而且深淺這個維度在畫布上
#不可靠 —— 縮放會改變抗鋸齒後的實際灰度，換暗色主題整組關係要重調。
#
#`canvas_edge_implicit` 是一個暖色，跟中性偏藍的 `canvas_edge` 拉開色相。
#測試鎖兩層：token 的色相差得出來，**而且 `paint()` 真的去讀了它**
#（兩條線各自畫進 pixmap 比主色相）—— 「token 換了但畫的地方沒改」正是要擋的。
#
#### 3. test 跟 ref 就是兩張不同的 image source
#
#原話：「很多張卡片都會限制或阻撓只能拉 ref……所以其實也不用再控制列設定什麼
#Apply to 或者是 also apply to（變很複雜）—— 之間用節點的方式去指引每張
#image source 會做哪些事。」
#
#七張 Enhance 卡本來是「`target` 主流 + `also_apply` 一串附帶的流」。
#那個形狀有三個問題，而且沒有一個是「多一個參數」而已：
#
#1. **它把 test 講成主角、ref 講成附帶。** patch 就是兩張輸入影像。
#2. **它讓一張卡偷偷動了畫布上看不到的東西。** 那張卡畫在 test 那條鏈上，
#   卻同時改寫了 ref —— **畫布因此說謊**，而畫布是這個工具的主體。
#3. **兩個節點之間只拉得動一條線。** 先從 test 拉、再從 ref 拉，第二條只會拿到
#   一句 `already connected` 然後什麼都沒發生。使用者的結論是「這張卡不准我碰
#   ref」—— 那就是回饋裡的「限制或阻撓」，而它其實是一個 UI bug。
#
#改法：`resolve_writes` 一律只回主流那一條，`also_apply` 從七張卡上消失。
#要對 ref 做同一件事就再放一張卡，畫布上因此看得到兩條各自的處理鏈。
#
#而 `edge_added` 多帶一個參數：**這條線從哪個輸出埠出發**。Studio 收到之後把下游
#那張卡的主要輸入指到那條流 —— 於是「這張卡做在 ref 上」變成一個**畫布上做得完**
#的動作。同一對節點再拉一條也照樣處理：那句話不是「你已經連過了」，
#是「我改變主意了」。
#
#### 4. 唯一掉了的能力，補一個看得見的替代品
#
#`percentile_norm` / `glv_mask_norm` 的 `anchor="source"`（其他流借主流量出來的
#拉伸範圍）是「兩張圖正規化完還比得起來」的關鍵，不能跟著 `also_apply` 一起消失。
#它現在是 `range_from` —— 而且它是一條**影像流的名字**，所以在畫布上就是接進這張
#卡的第二條線，不是藏在下拉裡的 `self` / `source`。借不到就報錯，不靜靜改用自己的
#範圍：兩者的輸出都是一張看起來很正常的圖，差別只在數字。
#
#### 5. 舊 recipe 要照樣讀得進來，而順序有陷阱
#
#recipe 是存在磁碟上、拿來交接的檔案。認不得 `also_apply` 等於一份跑得好好的檔案
#升級之後變成 `unknown parameters` —— 對不會寫 code 的人那就是「工具壞了」。
#`Recipe.from_json_dict` 加了一道遷移：一個節點展開成 N 張卡並插進 route。
#做在 recipe 層而不是卡片的 `validate_params` 裡，因為它**增加節點** ——
#一張卡看不到自己以外的東西。
#
#陷阱在順序：`anchor="source"` 的語意是「ref 用 **test 原本的** 範圍」。
#拆完之後如果 test 那張先跑，它會先把 test 拉成 0–255，ref 再去借就借到「拉伸後」
#的範圍 —— 數字不一樣，而兩張輸出都是看起來正常的圖。所以借範圍的那幾張排在
#**前面**。
#
#驗證方式不是讀程式碼：`die_to_die_basic` 跑 100 顆合成 patch，遷移前後
#`min / median / max` 與兩個 bin 的數量**逐項相同**（20.230 / 32.115 / 175.000、
#bin 0 = 54 · bin 1 = 46），`cd_gate` 同樣相同。三份範例 recipe 也就地改寫。
#
#### 6. 這個新形狀帶進來的新風險（還沒解）
#
#多數 recipe 會有一對 Normalize、一對 Denoise，而**它們必須維持同樣的參數才比得
#起來**。改了其中一張、忘了另一張，是 `also_apply` 時代不會發生的安靜失敗。
#候選解法是 lint 的一條 warning（「這兩條流被處理成不一樣了」），
#不是把兩張卡綁在一起 —— 綁起來就退回 `also_apply` 了。
#
#另外 `range_from` 的順序目前是靠參數說明講的：借範圍的那張要排在「會改寫那條
#流」的卡**前面**。遷移與 Studio 的加卡流程都會自然排對，手工重排才可能弄錯 ——
#而弄錯之後兩張輸出都是看起來正常的圖。
#
#新測試 `tests/test_ui_f7_18_streams_as_nodes.py`（11 個）。計畫書 §22。
#
#---
#
### 2026-07-28 · M6 推廣包（514 → 588 tests）· v1 功能齊備
#
#### 離線安裝三件套（對主要使用者最關鍵的一塊）
#使用情境是**沒有 git、pip 連不出去、DLP 擋含二進位壓縮檔**的公司機。
#`tools/fetch_wheels.py`（有網路的機器抓 Windows wheels，產 MANIFEST 含 sha256）→
#帶 `wheels\` 過去 → `tools/install_offline.py`（建 venv、`--no-index` 安裝）→
#`tools/doctor.py`（環境自檢）。三支都 **stdlib-only**，因為它們要在套件裝好之前就能跑
#（有測試用 ast 掃 module-level import 把這條約束鎖住）。
#
#`install_offline.py` 的八道 pre-flight 全部是「在 pip 之前就攔下來並講清楚」：
#最常見的失敗是 **wheels 的 Python 版本與機器上的不符**（cp39 輪子配 py3.12），
#它會讀 MANIFEST 比對、指出兩邊版本、給兩個選項。其餘涵蓋 requirements 找不到
#（→「你可能不在 ADEPT 資料夾裡」）、wheels 資料夾空的（→ 提示 DLP 可能吃掉了 zip）、
#磁碟空間、寫入權限，以及 `ensurepip` 被企業映像檔關掉時的 `--no-venv` 逃生路徑。
#
#`doctor.py` 逐項 ✓/✗/△ 並在每個沒過的項目附一行「怎麼修」，包含一個常見錯誤的
#專門偵測：**在錯的資料夾執行**（有 `adept\` 但 import 不到 → 直接叫他 cd）。
#Qt 能不能開視窗是在 **subprocess** 裡測的，這樣壞掉的 PySide6 不會把 doctor 一起帶走。
#
#### 首啟導覽
#`adept/ui/welcome.py`。核心是那顆**「用範例資料試一次」**按鈕：一按就自己產生合成資料、
#載入範本、跑完一批，使用者一分鐘內看到有分數的直方圖與 Gallery ——
#不需要先有真實資料、不需要先懂任何概念。導覽本身用三段式配色講清楚
#影像 → 算法 → ADC 判定 的心智模型。
#
#modal 不能污染測試，用了三層防護：constructor kwarg 自動偵測 `PYTEST_CURRENT_TEST`、
#`QTimer.singleShot(0, …)` 讓建構子永不阻塞、對話框一律 `show()` 不用 `exec()`。
#
#### 範例 recipe 庫（5 份，每份教一種作法）
#| recipe | 教什麼 |
#|---|---|
#| `die_to_die_basic` | 最典型：機台給 ref，對位相減 |
#| `dual_route_basic` | 一份 recipe 兩條 route，吃兩種輸入 |
#| `rsem_golden_cell` | 沒有 ref 就自己疊一張（且**不需要 norm 與 align** —— 自己減自己，增益偏移自動抵銷）|
#| `single_image_rules` | 完全沒有參考圖的保底流程：把口語規則寫成一條乘法算式 + 比較運算子當閘 |
#| `cd_gate` | 分數可以有物理單位：閘門確認真假、CD 決定重要性，門檻直接填「你在意的最小缺陷尺寸」|
#
#Agent 是**實測迭代**出這些算式的，不是照抄我給的建議 —— 例如原本建議 RSEM 用
#`blob_snr`，實測只有 ~55%，因為 `blob_snr` 在 uint8 SNR 地圖上會飽和在 255；
#改用 GLV 殘差才是誠實的贏家。`tests/test_example_recipes.py` 會確認每一份都能載入、
#validate 無 error、且真的能在合成資料上跑出有限分數 —— 這是防止範例庫腐爛的網子。
#
#### 暫緩
#快速參考卡 PDF 移到 backlog（使用者當下不需要）。
#
#### 狀態
#v1 規劃的六個 milestone 全部完成，588 tests。
#
#---
#
### 2026-07-28 · M5 Gallery + Export（347 → 514 tests）
#
#### Gallery（同屏比多顆）
#`adept/ui/gallery.py`：整個網格是**一個**自繪 widget（`QAbstractScrollArea`），
#只畫可視範圍 + 1 列 overscan，10 顆與 10,000 顆的 widget tree 完全相同
#（`set_items(10k)` 約 0.05 s）。QPixmap 轉換走 512 筆上限的 LRU。
#縮圖在背景執行緒解碼：gallery 發 `thumbs_requested(ids)` → Studio 的 `ThumbWorker`
#只解可視範圍那批（每批上限 48），in-flight 的 id 不重算。
#
#**直方圖點 bar → Gallery 篩選**是這一版的關鍵串接（調參迴圈的另一半）。
#難處在於同一個 widget 既要拖門檻又要點長條：解法是**在放開時才判定** ——
#按下時照舊記錄狀態，放開時若位移 > 3px 或按在門檻把手上就當拖曳，
#否則把門檻還原（並補發一次 `threshold_changed` 讓即時 bin 統計回捲）再發 `bar_clicked`。
#所以點長條保證不會動到門檻，兩種行為都有測試鎖住。
#
#### Export（三種 KLARF 寫回）
#`adept/core/export/`：
#- **inplace**：只走 `set_cell`，且值相同就不寫 —— 沒改到任何東西時輸出**逐位元組相同**（有測試）。
#  要求的欄位不存在時直接拋 `ExportError` 說明，不靜默略過。
#- **annotate**：1.2 改寫 `DefectRecordSpec`、1.8 改寫 `Columns N { … }`，
#  新欄位插在影像 token 起始欄之前，**影像區塊仍在列尾**；輸出重新解析後
#  `defect_image_map` / `load_dataset` 都仍正常。
#- **topn**：分數排序取前 N、DEFECTID 重新編號。**page 編號刻意不重映射**
#  （那需要一併重寫 TIFF），輸出檔必須與原 TIFF 放在一起 —— 這點寫進 plan 的 notes。
#
#UI 上最重要的設計是**「預覽變更」按鈕**：先跑 `plan_writeback` 乾跑，
#用白話列出會改幾列、動到哪些欄、新增哪些欄、健檢結果，預覽成功才解鎖「寫出」。
#任何控制項一改動就作廢重鎖。
#
#### fab_probe（廠內格式探測）
#三支 stdlib-only 單檔腳本，輸出純文字、預設遮蔽 Lot/Wafer/Device 識別碼，
#設計成可以複製貼出廠區。對應 CLAUDE.md §8 的三個假設。
#`probe_stats.py` 自己寫了 TIFF 解碼（未壓縮 / PackBits，8 與 16 bit，
#含 BigTIFF 與 big-endian），與 numpy 逐位元組比對驗證過；遇到解不了的壓縮
#會明講並跳過該頁而不是整支掛掉。
#
#### 順帶抓到並修掉一個真實資料上的 bug
#`probe_klarf.py` 跑在 `tests/fixtures/sample_real.klarf`（專案裡唯一一份真實來源的
#KLARF）上時發現**第四種變體**：`ImageList` 型別欄（IMAGEINFO）**不在最後一欄**，
#而且整份檔案沒有 IMAGECOUNT 欄。`row_len_ok` 原本用原始 token 數比對欄數，
#把佔 8 個 token 的 `Images 1 { … }` 當成 8 欄 → **每一列都被判違法**，
#`lint()` 對一份完全正常的檔案報 rowlen error。使用者會看到的症狀是：
#Export 精靈在寫回真實檔案前跳出嚇人的紅字。
#
#修法是加 `image_block_span()` / `effective_row_len()`，把子區塊折算成一欄。
#**刻意沒動 `image_layout()`** —— 它對這個變體回 None，而 export 的插欄位置
#正好因此落在最後，對這個變體來說是對的；「順手修好」它反而會把新欄位插錯位置。
#這點寫進 CLAUDE.md 的坑表了。迴歸測試 `tests/test_klarf_variant_d.py`。
#
#### 下一步
#M6 推廣包（離線 wheels 安裝、首啟導覽、範例 recipe 庫、快速參考卡）。
#
#---
#
### 2026-07-28 · M4 雙輸入 + Golden Cell（341 → 356 tests）
#
#驗收目標：**同一份 recipe 吃 EBI patch 與 Review SEM 兩種輸入**。達成，
#`examples/recipes/dual_route_basic.json` 跨 3 seeds × 2 種輸入共 144 顆合成 defect，
#分類正確率 95.1%（同一條分數表達式、同一個門檻）。
#
#### 補完 `period.choose_origin` 相位搜尋
#原本是回傳 `(0,0)` 的 stub。改為掃描 `[0,px) x [0,py)` 的候選原點，用
#`stack_cells` + `ghosting_score` 的**原始 Laplacian 變異數**（非 0–100 分數，
#後者在乾淨圖上會飽和而失去排序）挑最銳利的相位；候選數上限 ~256 再 ±2 微調，
#512² / pitch 64 約 0.5 s。誠實的但書寫進 docstring：對完美週期圖，重建本身
#與相位無關，所以這個準則是**平移等變**而非絕對 —— 它鎖定的是「cell 邊界對齊
#圖案最強邊緣」的相位。測試據此驗證等變性（裁切 c 像素 → 原點位移 −c mod pitch）。
#
#### 兩張新卡片
#- **`cell_period`**（算法段）：量出 X/Y 週期，寫進 `ctx.meta["cell_period"]` 供下游用。
#  沒有週期性是 warning 不是 error。
#- **`golden_cell`**（影像段）：疊出參考圖，預設寫入 `out="ref"` ——
#  **這個預設是關鍵設計**：下游所有吃 ref 的卡片完全不用改，
#  rsem route 只是多插一張卡就能重用整條 EBI 的算法段。
#  輸出會平鋪回原尺寸/dtype/通道數，確保能直接相減。
#
#### RSEM 合成資料產生器
#`tools/make_sample_rsem.py`：每顆 defect 一張 PNG + KLARF 1.8 的
#`Images N { "path" "PNG" 1 "24" }` 區塊（語法是讀 `klarf_core` 反推並 round-trip
#驗證出來的，不是猜的）。256²、pitch 24、每張隨機相位。`tools/_synth.py` 抽出
#與 EBI 產生器共用的晶格/植入缺陷程式碼，`make_sample.py` 輸出維持位元組相同。
#
#### 調 recipe 時撞到的兩件事（都寫進 CLAUDE.md 的坑表）
#1. **幾何參數與影像尺寸綁死**：同一組 `glv_stats` 中心框在 128² patch 上準，
#   在 256² RSEM 上漏抓六顆 —— 缺陷散佈範圍（±10% 影像寬）超出固定框。
#   解法：幾何類參數隨 route 走（兩條 route 各自一個 glv 節點）。
#2. **共用門檻需要無量綱分數**：兩條 route 的絕對 GLV 尺度不同，
#   `glv_max + (glv_max - glv_q99)` 各自能分開但沒有共用門檻窗。
#   改用穩健 z 分數 `(glv_max - glv_median) / (glv_std + 0.5)`
#   （「最強殘差高出典型殘差幾個 sigma」）後，兩邊共用門檻 4.2 成立。
#
#### 下一步
#M5 Gallery + Export（見 CLAUDE.md §9）。`fab_probe/` 廠內探測腳本從 M4 順延到 M5。
#
#---
#
### 2026-07-28 · M0–M3 + 專案命名（Claude Cowork session）
#
#從零建立整個專案。原工作代號 FlexADC，完成 M3 後定名 **ADEPT**。
#
#### M0 抽庫（117 tests）
#盤點六個既有專案（KLIP / GLAS / MMH / PEAR / cell-period-estimator /
#Perspective-Combination），把可重用演算法 vendoring 進 `adept/core`。
#決策：**vendoring 而非共用 library** —— 新工具完全獨立、不動現有專案。
#
#統一了三個歷史摩擦：
#1. ROI 座標 → 正規化座標（`NamedROI`）為正典，像素矩形一律 `(x,y,w,h)`。
#2. SNR 正負號 → `snr_signed = (μ_target − μ_ref)/σ_ref` 為唯一正典 primitive。
#3. `compute_snr_map` → 改回傳 `SnrMapResult(map_float, snr_max)`（原版回傳 tuple 與型別註記不符）。
#
#順手抓到 **Fusi³ `ecc` 對位 backend 位移正負號與其他四個相反**的 bug（原專案可回頭修）。
#
#### M1 引擎（223 tests）
#- `Context` / `Step` / `ParamSpec` / registry 契約（MMH recipe 架構的一般化：
#  寫死 6 stage → 任意 DAG 節點，並補上 MMH 缺的參數驗證）。
#- `Recipe`(DAG) + lint 式 `validate`（10 種 issue code，一次列出所有問題）。
#- score 表達式引擎：自寫 tokenizer → recursive-descent parser → AST → evaluator，
#  **不用 Python eval**；安全語意（除以零/log 負數/nan → 0.0，不爆給使用者看）。
#- 14 張步驟卡片、合成資料產生器、CLI。
#- **端到端驗收**：合成 lot（24 顆、真假各半）分類正確率 ~94%（跨 seed）。
#  調出這份範例 recipe 的過程本身就是工具價值的實證 —— 第一版完全分不開
#  （Otsu 在正規化 SNR map 上把半張圖切成 blob），靠 feature 表診斷 →
#  主 blob 選取從「面積最大」改「SNR 最強」→ 加 Denoise 卡 →
#  score 改用 diff 中心區 GLV 峰值，三輪迭代從 50% 拉到 94%。
#
#### M2 批次（245 tests）
#- ProcessPool 平行批次（單顆爆不殺整批、progress/abort）。
#- **影像段 checkpoint 快取**：快取邊界切在三段式的「影像段結尾」，
#  與 UI 心智模型對齊 —— 改算法段/判定段的任何東西都是秒級回饋。
#- SQLite 批次歷史 + **rescore**（改表達式/門檻不重跑影像）。
#- 實測（2 核容器、2000 顆合成 patch）：cold 17.5 ms/顆 → warm cache 2.2 ms/顆 →
#  rescore 0.17 s。換算 8 核廠內機 10k patch 約 1 分鐘。
#- 過程中發現 **OpenCV IPP 非決定性**（同圖算兩次差 ~1e-8，SIMD 路徑依緩衝區位址而變），
#  導致快取無法 bit-identical → `pin_cv2_deterministic()` 關閉 IPP。
#
#### M3 Studio UI（291 tests）
#- PySide6 四區塊：卡片庫｜Pipeline｜單顆預覽｜分數直方圖，三段式分色。
#- `RecipeModel` 是 Qt-free 的編輯模型（可 headless 測試），UI 元件只做顯示與轉發。
#- ParamForm 由 ParamSpec 自動生成，每格都有白話說明、範圍防呆、錯誤即時紅字。
#- PreviewWorker 請求合併（改參數狂發請求只跑最新那個）。
#- 拖門檻線即時看 bin 數變化（走 rescore 的純計算路徑，不碰影像）。
#- **修掉一個會讓工具在廠內「看起來當掉」的 bug**：`run_batch` 從 QThread fork
#  ProcessPool 在 Linux 上第二次必定死鎖（進度條不動也不報錯）。
#  修法：`batch._pool_context()` 主執行緒 fork（CLI/腳本免寫 `if __name__ == "__main__"`）、
#  非主執行緒 spawn。補迴歸測試 `tests/test_batch_thread_safety.py`。
#- 補上卡片庫「ADC 判定」段的固定 Score/Bin 項目，讓三段式故事在 UI 上完整。
#
#### 命名
#候選過水果系（PEACH/FIG/PLUM，與 PEAR 成家族）與非水果系，最後選
#**ADEPT = Auto Defect Evaluation Pipeline Tool** —— 縮寫精準對應功能，
#而 adept（熟練、得心應手）正是要給不寫 code 同事的承諾。
#套件 `flexadc` → `adept`、CLI `python -m adept`、設定目錄 `~/.adept/`。
#
#### 下一步
#M4 雙輸入 + Golden Cell（見 CLAUDE.md §9）。
#
#---
#
### 2026-07-28 · M7 UI/UX 檢討（Claude Code session）
#
#接手 session：先讀 `docs/HANDOVER.md`，然後做 UI/UX 體檢。使用者的實際感受是
#**「東西太多、太像玩具」**，逐條拆解後根因只有一個：
#**v1 的 UI 是按引擎的結構長出來的，不是按使用者的工作流程長出來的。**
#
#### 已完成：A 組（新手第一分鐘會撞到的四件事）+ UI 全英文
#
#- **A1 動作可用性**：前置條件不滿足的按鈕改成**變灰 + tooltip 說明原因**。
#  舊行為是全部亮著、按下去才在狀態列抱怨 —— 狀態列在螢幕最下角，
#  第一次用的人只會覺得「我按了，沒反應」。新增 `_update_action_states()` 單一決策點。
#- **A2 游標讀數搬家**：`ImageView.cursor_info` 原本直接接到狀態列，
#  滑鼠飄過影像就把「試跑完成：100 顆…」洗掉。改成預覽區自己的標籤，
#  狀態列只留事件訊息。
#- **A3 工具列去重**：「載入範本（die-to-die）」與「範例 recipe」做的是同一件事
#  （都在載 `examples/recipes/` 的 JSON），且 die-to-die 對目標使用者是行話。
#  合併成單一入口「Templates…」。
#- **A4 主要動作只留一顆**：「全跑」收進「▶ Run trial」的下拉。
#  試跑筆數改成跟著資料集走（24 顆的 lot 不再顯示「First 200」）。
#- **UI 全英文**：使用者原話「中英夾雜很混亂」。工具列、面板、對話框、
#  卡片 label/help、ParamSpec help、參數與 recipe 驗證錯誤、score 表達式錯誤、
#  KLARF 寫回計畫書、CSV/Excel 報表標題全部英文化。
#  **docstring 與註解維持中文** —— 那是開發文件，是這個 repo 刻意累積的資產。
#  新增 `tests/test_ui_english_only.py` 走 AST 把不變量鎖住（只管字串常數，
#  docstring 節點跳過）；`__main__.py`（CLI 是另一個介面層）與 vendored 的
#  `klarf_core.py` 列在 PENDING 並註明理由，另有一個測試防止清單發霉。
#
#595 tests 綠。
#
#### 討論定案：F7（見 `docs/plans/F7-canvas-and-taxonomy.md`）
#
#三輪來回之後定下的方向：
#
#- **patch-only 收斂**（RSEM 先關掉但**不刪 code**）。刪掉等於丟掉整個 M4；
#  而且 `algo/period.py` 的相位搜尋是之後做 pattern-frame ROI 的唯一工具。
#- **卡片改依流程階段分類**：Input → Enhance → Region → Compare → Measure → ADC → Output，
#  每段附一條型別規則（吃什麼、吐什麼），新卡片放哪不用討論。
#  舊的「影像／算法」分的是**輸出型別**，不是**使用者意圖** —— 那是「太武斷」的根因。
#- **ROI 升成一級概念**。查證後發現 `Context.rois` / `Context.labels` 與
#  `algo/roi.py` 的 `NamedROI` / `MultiROISet` **早就存在但從來沒有人寫過**
#  （`context.py:33` 的註解寫著「M3 起由 ROI 卡填入」，那張卡沒做出來）。
#  ROI 現在是散在各量測卡裡的 `region=` / `box_size` 參數，正是 CLAUDE.md §7
#  那個「中心框幾何與影像尺寸綁死」的坑。
#- **但 Region 段先不照搬**：使用者指出機台的裁切是「以 defect 為正中心裁 x×x」，
#  所以 patch 裡有兩個座標系 —— **defect frame**（中心固定，穩定）與
#  **pattern frame**（晶格相位逐顆不同，不穩定）。v1 只做 defect frame 的 ROI。
#- **Align 降級**：使用者的領域知識 —— 機台輸出的 patch 兩兩對應本來就是
#  defect & reference，不需要對位。卡片保留但不進預設範本。
#  驗證方法已記在計畫書：`align_dx` / `align_dy` / `align_score` 都是 feature，
#  拿真實 lot 跑一次看 CSV 的分佈就知道。
#- **視覺目標是 n8n / KLIP 的語言**（中性灰、全平面、顏色只表達語意）。
#  現在的暖奶油 + 琥珀是 vendoring 自 CPE 的；使用者自己的 KLIP 已經是想要的風格。
#- **Output 是固定尾節點但底下仍是 Export 精靈** —— ADC 是 per-defect、
#  Export 是 per-batch，不該真的變成流程節點。
#
#### 下一步
#
#F7-1 patch-only 收斂 → F7-2 主題換色 → F7-3 卡片分類 → F7-4 Region 段 +
#量測卡遷移（破壞性 schema）→ F7-5 Results 視窗 → F7-6 畫布。
#
#`fab_probe/` 的三個原始假設仍然全部未驗證，優先度不因這次重構而降低。
#
#### F7-1 patch-only 收斂（603 tests）
#
#新增 `adept/ui/scope.py` —— **一個檔案就是整個開關**：
#
#```python
#SUPPORTED_KINDS = ("ebi_patch",)                 # 加 "rsem" 就整條路線回來
#HIDDEN_STEPS = ("golden_cell", "cell_period")    # 清空就出現在卡片庫
#```
#
#GUI 側的三個切點：
#- 卡片庫過濾（17 列 → 15 列，掉的正好是最難懂的兩張）
#- 載到 rsem 資料集 → **擋下並講清楚原因 + 給替代路徑**（CLI 仍跑得動），
#  而且**不動既有狀態** —— 開錯一個檔不會把使用者正在調的東西弄丟
#- 範本庫過濾：判準是「至少有一條看得懂的 route」而不是「只有看得懂的 route」，
#  所以 `dual_route_basic` 照列（載進來走 ebi_patch），只有純 rsem 的被收起來
#
#`tests/test_ui_patch_only.py` 鎖兩件事，第二件才是重點：
#1. GUI 真的收斂了
#2. **core 一行都沒少**，而且「打開開關就回得來」是有測試保護的事實 ——
#   那支測試會 monkeypatch 兩個常數再驗一次整條 RSEM 路線
#
#裡面有一條 `test_period_module_is_not_orphaned`，作用是一張便利貼：
#`algo/period.py` 現在只被 Golden Cell 用到，看起來像可以陪葬，
#但它是之後做 pattern-frame ROI 的唯一工具。
#
#順手補完英文化漏掉的東西：**9 處全形標點**（`、`、`：`、全形空白 `　`）。
#`_has_cjk` 已擴到涵蓋 CJK 標點與全形 ASCII 變體 —— 標點是翻譯時最容易漏的。
#
#### F7-2 主題換色 + 平面化（607 tests）
#
#`TOKENS` 的**鍵名一個都沒改**，只換值 —— 所有顏色本來就集中在這裡
#（同時餵 QSS 與自繪 widget），所以換膚零呼叫端改動。
#暖奶油 `#f7f4ef` + 琥珀 `#f29f4b` + 填滿色塊 → 中性灰 + 克制的藍 + 細色條。
#新增 `PALETTES` 的 light/dark 兩組（鍵名逐一比對），`set_theme` **就地更新**
#`TOKENS`（不能換掉物件，各模組都 import 過它了）。工具列一顆 `◐` 切換，
#偏好存 QSettings。
#
#三個舊測試把暖色 hex 寫死了，改成斷言**性質**：大面積底色中性（RGB 極差 ≤ 8）、
#QSS 無陰影無漸層、雙色盤鍵名一致、`set_theme` 就地且可逆。這樣微調配色不會一直打壞測試。
#
#### F7-3 卡片分類重整（611 tests）
#
#`Step` 新增 `group`（與 `category` **獨立的軸**）：
#`category` 是引擎用的（快取切點、驗證順序），`group` 是使用者用的（卡片庫分組）。
#舊 UI 直接拿 category 當分類，於是使用者看到「影像／算法」—— 那描述輸出型別，
#不是意圖，這就是「太武斷」的根因。
#
#新分段：**Input → Enhance → Region → Compare → Measure → ADC**，
#每段附一條機械可判定的規則（吃什麼、吐什麼）寫在 `step.py` 的常數旁邊。
#`resolve_group()` 有依 category 的 fallback（外掛卡不會壞），但另一支測試要求
#**本 repo 內建的卡片一律明講** —— 否則新加的量測卡會安靜地掉進 Enhance。
#
#另外兩件讓 15 列不再瑣碎的事：搜尋框（比對名稱/key/說明/group）、
#前置條件 badge（`needs diff`，調淡但**仍可加入** —— 卡片庫順序不是執行順序）。
#區塊標題從填滿色塊改成 **QPainter 畫的 icon + 標題**（不加任何圖檔，
#顏色吃 token 所以跟著換膚）。
#
#踩到一個坑：`isVisible()` 在視窗 `show()` 之前一律是 False，
#headless 測試會全部誤判 —— 可見性與 badge 一律改用明確狀態。
#
#### F7-4 Region 段 + 量測卡遷移（623 tests，破壞性 schema）
#
#**ROI 從「藏在量測卡裡的參數」升成一級概念。**
#`Context.rois` / `algo/roi.py` 的 `NamedROI`/`MultiROISet` 從 M0 就存在、
#但從來沒有人寫過（`context.py:33` 註解寫著「M3 起由 ROI 卡填入」，那張卡沒做出來）。
#現在 `Context` 包了一層**以名字為鍵**的 API（`set_roi`/`require_roi`/`roi_rect`），
#底層仍用 MultiROISet 的 `label`，不另外發明資料結構。
#
#- 新卡 `roi_define`：`shape=center|whole`、`size` + **`size_unit=px|percent`**
#- `blob_segment` 的主 blob 也發布成具名 ROI（預設 `blob`）——
#  偵測出來的框與手畫的框走同一條路，這是最關鍵的一刀
#- `glv_stats`：`region`/`box_size` → `roi=<名字>`
#- `roi_snr`：`mode`/`box_size` → `roi=<名字>`
#- `cd_measure`：新增 `roi`（預設 `blob`）
#- 5 份範例 recipe 自動遷移（插入 `roi_define` 節點）
#
#**`percent` 修掉 CLAUDE.md §7 那個坑**：同一份 recipe 在 128² 與 256² 上
#看的是同一塊相對區域（`(48,48,32,32)` vs `(96,96,64,64)`）。
#
#驗收：`die_to_die_basic` 跑 100 顆合成 patch，分數分佈與重構前**逐項相同**
#（min 21 / median 45 / max 171、bin 0=52 · bin 1=48），對照 ground truth 98%。
#行為完全保持。
#
#`roi='blob'` 存的是像素座標，所以**不需要影像**就取得到 —— 下游把影像流蓋掉
#之後 CD 還是量得到（有測試鎖）。
#
#### F7-5 Results 視窗（632 tests）
#
#主視窗一直是四區塊 + 底部全寬直方圖，「編流程」與「看整批」擠在同一個畫面。
#拆的界線是「這個東西要不要先跑過一批才有意義」：
#
#- 主視窗 Workspace：編流程 · 看單顆 · 調參數（三欄，**預覽拿最寬的一欄**）
#- Results 視窗：分數分佈 · Gallery · 輸出
#
#`ResultsWindow` 沿用 `WelcomeDialog` 的慣例（自己不驅動任何東西，只發訊號）。
#非 modal，關掉不丟結果。
#
#**這個改動最容易弄壞的東西已經用測試鎖住**：拖門檻線仍然走
#`viewmodel.rebin()` 的純計算路徑（拖曳中不寫 model、放開才 commit）。
#那是調參迴圈一半的價值，換視窗時最容易被接成「每動一次就重跑」。
#
#兩個測試環境的坑：`QSplitter.sizes()` 在視窗 show 之前沒有意義（欄寬測試改斷言
#設定常數 `COLUMN_SIZES`）；`_maybe_request_thumbs` 對相同可視範圍會提早 return，
#而這批全部塞得進畫面 —— 縮圖測試要重置那個備忘，不是硬去改視窗大小。
#
#### F7-6 節點畫布（643 tests）
#
#`core` 從 F0 起就是 DAG（`Recipe.edges`、Kahn 拓撲排序 + 循環偵測都在），
#當初就寫著「之後上自由畫布時引擎零改動」——**這次證實了**：
#`adept/ui/canvas.py` 是純 UI，core 一行沒動。
#
#- `RecipeModel` 新增 `edges`；`node_order` 改由拓撲排序算出（同層維持原相對順序，
#  拉一條線不該讓別的節點亂跳）
#- `PipelineCanvas` 的公開 API 與訊號**刻意與舊的 `PipelinePanel` 對齊**，
#  所以 Studio 的接線幾乎沒動 —— 換 UI 不要順便變成重寫主視窗
#- **循環擋在 `add_edge`**：會成環的線直接回 False 不落地。
#  使用者看到「這條線拉不起來」，而不是「拉起來之後跑的時候才爆」
#- 排版是自動的（拓撲深度分欄）。位置**不寫進 recipe** ——
#  為了存座標而改 JSON 格式會讓每份既有 recipe 都要遷移，代價和收益不成比例
#
#M7 至此完成。643 tests 綠。
#
#### CI 修正：`pytest` vs `python -m pytest`（643 tests）
#
#PR #1 開起來之後 CI 三個 job 全紅，錯誤是 `ModuleNotFoundError: No module named 'adept'`
#—— **收集階段就中斷，一個測試都沒真的跑到**。
#
#根因與這次的改動無關，是 pre-existing：
#
#| 指令 | CWD 進 `sys.path` 嗎 | 結果 |
#|---|---|---|
#| `python -m pytest -q` | 會 | 找得到 adept ✓ |
#| `pytest -q` | **不會** | ModuleNotFoundError ✗ |
#
#CI（`.github/workflows/ci.yml`）跑的是後者，本機開發（以及這整個 session）用的是前者，
#所以這件事從 CI 加進來（commit `de387c5`）之後一直沒被發現。
#
#修法：新增根目錄 `conftest.py`（pytest 載入 conftest 時會把它所在的目錄插進
#`sys.path`），裡面再明確補一次 repo 根與 `tools/`，讓意圖看得出來、
#也不依賴 pytest 的 import-mode 細節。
#
#**沒有選 `pip install -e .`** 的理由：廠內機器是解壓 zip 直接跑
#（見 `docs/NO-GIT-SETUP.md`），「從 repo 根目錄直接跑得動」是這個專案要維持的性質。
#
#修好之後 CI 終於跑到底，露出第二個問題：**636 passed, 6 skipped, 1 failed** ——
#workflow 手寫的 pip 清單漏了 `openpyxl`（它在 `pyproject.toml` 與 `requirements.txt`
#都是硬相依）。三支 Excel 報表測試用 `pytest.importorskip` 安靜跳過，
#所以這個缺口一直藏著，直到有一支測試真的斷言匯出要成功才爆出來。
#
#除了補上套件，workflow 多一步：裝完之後逐項確認 `requirements.txt` 的東西
#都 import 得到，漏了就指名報錯。安裝清單不能直接寫 `-r requirements.txt`，
#因為 CI 刻意把 `opencv-python` 換成 headless 版 —— 而那種「刻意的分歧」正是
#會安靜漂移的東西，所以用測試守住而不是靠人記得。
#
#結果：3.9 / 3.11 / 3.12 三個 job 全綠，**643 passed、零 skip**。
#註腳：在此之前所有「N tests 綠」都只在 `python -m pytest` 下成立；現在兩種都成立。
#
#驗證方式也記一下：本機 PATH 上第一個 `pytest` 是 uv 裝的獨立工具（自己的 venv、
#沒有 numpy），跟 CI 的情況不同 —— 要用與 `python -m` 同一個直譯器的那支
#（`/usr/local/bin/pytest`）才驗得準。加了 conftest 前後各跑一次確認因果。
#
#### F7-7 / F7-8：試用回饋兩輪（679 tests 綠）
#
#使用者實際開起來用之後提的事情，分兩批做完。
#
##### F7-8 之一：數字參數配滑桿 + 自訂色調曲線
#
#> 「調亮度 對比可以放在一起，然後是用搖桿調整（不是輸入），同理 gamma 也是。
#> 然後下方要支援 custom curve 可以自己畫 gamma 曲線（預設 y=x）」
#
#滑桿是**資料驅動**的：ParamSpec 有 `min`/`max` 就自動配一支，沒有就不配。
#新卡片把上下界填好（本來就是鐵則 4 的要求）就自動有滑桿，UI 零登記。
#數字框刻意留著 —— 滑桿負責「找到大概的位置」，數字框負責「記錄與重現」，
#recipe 是要交接給別人的。
#
#曲線存成字串（`"0,0; 0.35,0.6; 1,1"`）：ParamSpec 的值一律是純量，
#UI 表單 / rescore / CLI `--set` 全靠這條規則；而且 recipe 的 git diff
#仍然一眼看得出「使用者把暗部拉起來了」。
#
#**插值用保單調三次 Hermite（Fritsch–Carlson），不是自然三次樣條。**
#自然樣條會 overshoot —— 使用者把中間點往上拉，曲線在旁邊先往下凹一段，
#影像上就是一圈**演算法自己造出來的暗環**。對一個要拿去判 defect 的工具來說，
#那是最糟的一種 bug。`tests/test_curve.py` 用四條最容易凹出去的曲線鎖住。
#沒有引進 scipy（廠內離線機，相依愈少愈好）。
#
#曲線與 gamma 是**接手**不是疊加：疊加的話「我把曲線拉平了怎麼還是暗」
#會非常難 debug。UI 因此在曲線生效時把 gamma 那列**調淡並說明原因** ——
#但不 disable，使用者可能只是想比較兩種做法。
#
#編輯器畫的線就是影像上套的線（同一個 `algo.curve.curve_lut`）。
#UI 自己再實作一份插值太容易發生，那會讓看到的和跑出來的不一樣。
#
##### F7-8 之二：畫布殘影、成對的線、並排看兩張圖
#
#殘影的原因是 `boundingRect()` 沒涵蓋畫在節點右緣**之外**的埠標籤 ——
#Qt 只重繪你宣告的範圍。已記進 CLAUDE.md §7。
#
#Input → Subtract 現在畫**兩條**線（test 一條、ref 一條）。這是從兩端共用的
#影像流**推導**出來的，不是存起來的：recipe JSON 的 edge 仍然是 `[from, to]`，
#格式不用改，重新載入不掉資訊。
#
#**並排比對預設關著。** 使用者問「還是你覺得秀一張比較好」——
#F7-5 把 Gallery 與直方圖搬走就是為了讓右欄的影像變大（原話「影像最好大一點」），
#預設並排等於把剛爭取到的寬度再砍一半。真正需要並排的時機很明確：
#**調 Enhance 卡的時候**，確認 test 與 ref 被調成一樣的。那是一次點擊。
#開了之後兩張圖的縮放與平移**連動** —— 沒有連動的並排，使用者得自己把兩邊
#拖到同一個位置才比得起來，那還不如切換一張。
#
##### F7-8 之三、四、五：直式 rail、Normalize、畫布視覺
#
#左側六個階段的大 icon 由上而下排成一條工作列；卡片區收起來時整欄只剩 rail，
#寬度真的還給工作區。**搜尋框住在卡片區裡**，所以 rail 底部必須留一顆放大鏡 ——
#不然卡片區收起來之後搜尋就再也叫不出來了（差點漏掉這件事）。
#
#Normalise → Normalize，三張卡改成共同前綴（`Normalize · Percentile` / `· GLV band`
#/ `· Histogram match`），在清單裡自然排在一起。
#
#畫布視覺：n8n 之所以一眼認得出來，靠的是**左邊那顆有顏色的圖示磚**，
#不是細色條 —— 細條太安靜，遠看還是一排一模一樣的方框。所以加了圖示磚
#（淡色底 + 與 rail 完全相同的圖形）、投影、**點陣底而不是格線底**
#（格線跟連線同一種筆觸，「哪條是資料流」要看第二眼）、連線中點的方向箭頭、
#停用節點畫虛線框。過長的文字一律 elide —— 硬切在字中間的
#`source=diff · metri` 會讓人以為參數值真的是那樣。
#
##### 一個自己造的坑
#
#`s.replace('self._scroll = QScrollArea(self)', ...)` 沒有加錨點，
#把 `LibraryPanel` 以外的兩個類別（`ParamForm`、`PipelinePanel`）一起改了。
#全域字串取代改 Python 原始碼要先確認那行字在檔案裡是唯一的。
#
#計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §12。
#
#---
#
### F7-9 —— 試用回饋第三輪（2026-07-29）
#
#使用者提的四件事 + 一個提問。最後那句話才是真正的目標：
#**「希望兩張 patch 可以一起，或經過不同的工作流做設定」**。
#前四件事看起來各自是小毛病，但都指向同一個缺口 ——
#**「影像流」這個概念在畫面上幾乎是隱形的**，而「兩張要一起還是分開」
#正好是一件純粹關於影像流的事。
#
#### 1. 六個階段六個顏色
#
#以前是 `group → category → 顏色`，category 只有三個，所以六個階段三種色
#（Input／Enhance／Compare 全是藍的）。圖示分得出來、顏色分不出來。
#新的 `theme.group_hex()` 每階段一個色相，挑色條件是**可驗證的性質**：
#兩兩 CIE Lab ΔE ≥ 25（看得出是兩個顏色，不是同色深淺）、
#同主題內明度 L\* 差 ≤ 15（像一套色票）。兩條都有測試鎖，色碼還可以再調。
#`seg_hex()` 沒被取代 —— 需要講「這是哪一段」的地方仍然用它。
#
#### 2. 一個 bug，兩個症狀
#
#「移動 Load images 有殘點」與「新增的節點只有前面有圓框、後面沒有」
#**是同一個 bug**：`paint()` 拿場景座標去畫本地座標的東西。
#節點在原點時看起來正常 —— 而第一欄的 Input 剛好在原點，所以症狀才會長成
#「Load 有埠，後面的卡沒有」。
#
#F7-8 修過一次殘影，改的是 `boundingRect` 的大小。那是對症狀動刀，所以它又回來了。
#真正的不變量是**畫的座標系＝宣告的座標系**：現在分成 `out_anchors_local()`
#（繪製、命中判定）與 `out_anchors()`（連線），測試直接鎖「拖到哪裡，
#每個埠與標籤都要在 `boundingRect` 裡」。
#
#順手：輸入埠空心、輸出埠實心；**每個輸出埠都標上流名**（以前只有多埠才標）。
#
#### 3. 起手卡
#
#空白畫布對不會寫 code 的人是一道關卡，而答案永遠是同一個。
#`RecipeModel.starter()` 開窗就放好 Input 卡並選起來，`dirty=False`
#（什麼都還沒做，不該被問「要存檔嗎」）。
#
#### 3b. 還沒拉線的畫布會換行
#
#截圖檢查時發現的（不在回饋清單上）：九張還沒拉線的卡排成一列超過 2500px，
#`fit()` 只能縮到看不出字 —— 而它有下限，所以結果是「一排讀不出來的小方塊
#**加上** 一條捲軸」，兩邊都輸。退化排版現在每 4 張換一行。
#
#### 4. target / also apply
#
#提問本身就是答案：使用者在畫布上想的是**節點**，這兩個參數講的是**影像流** ——
#流是節點之間的**線**。以前畫面上沒有任何東西說出這件事。
#所以：`ParamSpec.label`（顯示名，`name` 仍是 JSON 的鍵）、
#新型別 `image_keys`（值的格式沒變、舊 recipe 照讀，但 UI 給勾選框）、
#說明改寫成「流就是畫布上那些有名字的線」、每個輸出埠標上流名。
#
#於是使用者要的那件事變成一個看得見的動作：
#**ref 勾著＝兩張一起；取消＝分開**。
#
#### 5. 點卡片跳到 ref
#
#`_default_stream()` 取「這張卡寫過的最後一條流」，而 Enhance 卡的 writes 是
#`[target] + also_apply` —— 最後一項永遠是 `ref`。改成先看主要參數
#（`target`/`source`）。另外加一條保險：左右算出同一條流時右邊讓步 ——
#兩張一模一樣的圖是並排唯一沒有意義的狀態。
#
#### 6. 卡片組合的稽核（使用者的提問）
#
#把 19 張卡的 reads/writes/features/具名區域全部攤開跑過，兩個真的會咬到：
#
#- **具名 ROI 完全沒被檢查。** 影像流有 reads/writes 可以在 `validate()` 裡模擬，
#  ROI 沒有。`cd_measure` 預設 `roi="blob"`，少了上游 Blob 卡就**安靜地改量整張
#  圖** —— 跑得完、有數字、而且是錯的。這是最糟的一種：看不出哪裡不對。
#  修法是讓區域走同一條路（`resolve_regions_in/out` + `unknown-region`），
#  退回整張圖時 `ctx.warn`。
#- **Studio 從來沒跑過 lint。** 同一份檢查 CLI 從 M1 就在用。加上「單顆出錯不殺
#  整批」的契約，接錯的卡片會**跑完 200 顆、每顆都失敗**。現在試跑前先 lint。
#
#**沒有動 `subtract` 的預設值**（它吃 `ref_aligned`，所以 Load 之後直接放
#Subtract 一定缺上游）。改成 `ref` 會讓它立刻能跑，但接著會產生一個更難發現的
#反向陷阱：加了 Align 卻沒重新接線 → **安靜地減掉沒對位的 ref**。
#用一個看得見的錯誤換一個看不見的錯誤，不划算。改成在加卡片時把話講完：
#「還缺 ref_aligned（先加 Align），或指到現有的 test / ref」。
#
#### 7. 一個順手清掉的地雷
#
#`test_no_qt_after_import` 以前在測試行程裡看 `sys.modules`，所以它**跟檔名的
#字母序有關** —— 新增一支排在它前面的 UI 測試檔就會誤報，而訊息指不到真正的
#原因。改成在乾淨的子行程裡 import core 再問。
#
#計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §13。測試：`tests/test_ui_f7_9_feedback.py`。
#
#### 8. 卡片組合稽核挖出的兩個 bug（同一個 session）
#
#**快取只存了 Context 的一部分。** checkpoint 是執行順序上的**位置**（最後一張
#影像段卡的下一格），不是「所有影像段的卡」，所以「載入 → 先框出要看的地方 →
#再做影像處理 → 量測」這個**很自然**的順序，會把 Region 卡（algo）夾進快取段。
#v1 快照只存 images/features/meta，`ctx.rois` 沒存 —— 於是**第一次跑對、第二次
#跑錯**（`region 'main' is not defined`）。先寫出重現再修。快照現在涵蓋 rois 與
#labels，並帶 `FORMAT_VERSION`：版本不合當 miss，既有快取目錄不會把殘缺快照
#餵回來。迴歸測試刻意先斷言「checkpoint 真的吞掉了那張 Region 卡」，
#免得哪天切點改了、測試還在綠但已經沒測到那條路。
#
#**特徵是扁平的全域命名空間。** 兩張同型別的量測卡寫同一組名字，
#所以「量中心 + 量整片」這個一定會做的事，跑完只剩後面那張的值，
#而且前面那個**完全沒有辦法**從分數表達式指到。lint 以前說這份 recipe 是乾淨的。
#現在是 `feature-collision` warning，Studio 跑完在狀態列講出來（跑之前講會被
#「Running: 3 / 200」洗掉）。不擋執行 —— 同名覆寫有時是刻意的。
#根治要讓量測卡能自訂輸出名，那件事跟 ROI 段一起做。
#
#---
#
### F7-10 —— 隱含順序 + Enhance 空間性 artifact（2026-07-29）
#
#### 1. 畫布上「沒有線」不代表「沒有連接」
#
#引擎的依賴從 M1 起就是「route 相鄰對 ∪ 顯式 edges」，但畫布只畫後者。
#載入沒拉過線的 recipe 看到的是九張互不相干的卡，而它其實照順序在跑。
#現在 route 相鄰對畫成虛線、半透明、**不可選取**（刪掉它等於「把卡片從流程裡
#拿掉」，那是另一個動作）。使用者親手連同一對時換成實線，不會變兩條。
#
#副作用：每份 recipe 現在都有依賴，所以 F7-9 只做在退化排版上的換行要對深度排版
#也成立 —— 不然九張卡又排成一條 2500px 的橫列。
#
#### 2. Enhance：六項能力，兩張新卡
#
#使用者的要求是「不要開太多卡片，類似的放一起」。所以：
#`flatten`（背景／條紋／top-hat／black-hat 五個方法一張卡）、
#`local_contrast`（CLAHE，掛進既有的 `Normalize ·` 家族）；
#邊緣保留去噪塞進既有 `denoise` 的 method 下拉；
#雙流運算塞進既有 `subtract` 的 op 下拉。19 → 21 張卡。
#
#`flatten` 的五個方法看起來是五種東西，其實是同一個結構：估一個大尺度成分再減掉，
#差別只在怎麼估。這種時候就是同一張卡的一個下拉。
#
#**兩個實作決定值得記：**
#
#去條紋用**中位數**不用平均 —— 一顆夠大的缺陷會把該列平均帶偏，校正時就在缺陷
#那一列造出反向假條紋。演算法自己造缺陷，跟 F7-8 的曲線 overshoot 同一類。
#
#保留邊緣的去噪，強度以**這張圖自己的雜訊 σ** 為單位（Immerkær 估計），不是灰階
#常數。給常數的話換台機台就不對，而使用者只會覺得是自己參數調錯。實測 h≈1σ 雜訊
#掉九成、3×3 缺陷完好；2σ 起缺陷開始消失，所以預設停在 1。
#
#加 bilateral/nlm 的唯一理由是 median 對「比核心小的亮點」是毀滅性的 —— 而那正好
#是要找的東西。測試拿 median 當對照：同一顆缺陷 median(5) 從 46 抹到 5，
#bilateral 與 nlm 都留在 46 以上。
#
#計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §14。
#
#---
#
### F7-11 —— ROI 定位第一批（2026-07-29）
#
#### 起點：一個把我原本設計推翻的領域事實
#
#patch 是 EBI 機台以缺陷位置為正中心裁出來的，所以**缺陷永遠在中央**；
#而 EBI 的檢測本來就鎖定在某一種 pattern 上，所以**每張 patch 裡一定有那個結構**。
#但缺陷可能落在結構中間、也可能靠邊 —— **結構在 patch 裡的位置逐顆不同**。
#
#所以「中心固定框一定準」只對了一半：缺陷本身在中央沒錯，但缺陷**周圍**的東西
#每張都不一樣。框只要大過缺陷就可能吃進別種材質，數字忽高忽低，而變動的原因
#不是缺陷。拿來當背景的區域更糟。
#
#問題因此不是「把框放在畫面的哪裡」，是**「把框放在結構的哪裡」**。
#
#### 做了什麼
#
#1. **量測卡自訂輸出名**（`output_prefix`，前置）。沒有它，兩張量測卡的特徵會
#   互相蓋掉，多區域整件事不成立。Studio 在使用者挑了區域之後**自動填成區域的
#   名字** —— 命名空間是工具的問題，不是製程工程師該懂的事。只在空著時填。
#   順帶給 `ParamSpec` 加了 `pattern`，把「不能當變數名的前綴」擋在驗證層。
#2. **投影定位卡** `roi_profile`：把影像壓成曲線 → 找轉折 → 挑一段當具名區域，
#   可以一次吐出選中的那段與左右鄰段（訊號要跟**同一種材質**的背景比才有意義）。
#3. **曲線面板**：曲線、轉折線、選中的段、中心線、信心值。
#
#### 幾個想清楚才寫下去的決定
#
#**找轉折，不分材質。** 第一版想「EPI 暗、MG 中、交界最亮 → 分三種灰階」，
#被使用者一句話擋掉：這個工具是泛用的，之後的資料不會只有這幾種 layout。
#分材質要先知道有幾種、每種多亮，而灰階會隨機台漂移 —— 等於把 recipe 綁死在
#一種 layout 上。找轉折只問「哪裡在變」，使用者只要回答「我要哪一段」。
#
#**在 ref 上找，不在 test 上。** test 上有一顆缺陷正在破壞結構。
#
#**定不出來就講出來。** 整張同一種材質的 patch 不可能定位 —— 那是資訊不夠，
#不是演算法不夠。但它也不需要定位（整張量就是對的）。所以退回整張圖並標記
#`locate_ok=0`，讓使用者事後分得清哪些顆是定位過的。
#
#**信心的分母要用 MAD 不是標準差。** 銳利的邊界會讓平滑吃掉一點真訊號，
#用標準差當分母會變成「結構越清楚、信心越低」，完全相反。
#實測：均勻約 0.7，有結構的都在 20 以上。
#
#**固定斜率的漸層要擋掉。** 每一格梯度都相等，不防的話浮點誤差決定邊界畫在哪，
#而且每格都被判成邊界。要求最陡處至少比一般處陡 1.2 倍
#（漸層 1.00、正弦 1.41、方波極大）。
#
#**面板畫的是引擎算的那一份**（走 `ctx.meta["profiles"]`），UI 不自己再算 ——
#不然「畫面上的框」跟「真的量下去的框」有機會不一樣。
#
#### 面板揭出來的一個舊 bug
#
#`PreviewWorker` 只合併「還沒開跑」的請求；已經在跑的那筆照樣會發 ready。
#所以「先送背景預覽、接著跑同步預覽」時舊的那筆會**後到**，把新畫面蓋掉，
#而且不會再更新。以前的症狀是「影像閃一下」，不容易歸因；曲線面板讓它變成
#「面板整個空白」才浮出來。修法：預覽加世代編號，過期的整筆丟掉。
#
#計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §15。
#下一批：Golden Cell 模板比對（零件 period/golden/align 都已在 repo）。
#
#### F7-11 第三批：區域跨顆檢視
#
#區域設定對不對是一個**關於整批**的問題 —— 在第 1 顆剛好的框，第 50 顆可能整個
#偏掉，而看單顆永遠看不出來。所以 Region 卡旁邊多了一顆按鈕，把區域畫到前 N 顆
#的縮圖上一次看完，失敗的用外框標出來，並且可以**只看失敗的**（那些才是要看的：
#可能本來就沒結構可認，也可能是參數太緊，只有看圖分得出來）。
#
#按鈕對**任何**會定義區域的卡片都出現，不是只給投影定位卡。
#
#一個容易腐爛的地方先鎖起來：縮圖的 letterbox 偏移 (`thumb_placement`) 與
#`make_thumb` 放在同一個檔案，而且測試拿兩者對照 —— 分開放的話，改了縮圖的縮放
#規則而忘了改另一邊，框會整批偏掉，但畫面上只看得出「框好像有點歪」。
#
#---
#
### F7-12 —— Golden Cell 模板定位（ROI 定位第二批）（2026-07-29）
#
#投影定位只看 patch 自己，patch 裡沒地標就定不出來 —— 而 patch **普遍小於一個
#重複單元**，那不是例外是常態。這一輪補上另一條路：把資訊從外面帶進來。
#
#### 使用者自己提出的解法（而且是對的）
#
#「patch 比 cell 小，對得起來嗎？」→「匯入一張原大圖，用 cell period 疊出 Golden
#Cell 當模板。」
#
#對的，理由值得記：**模板法不是把兩張小 patch 互相對位，是把一張小 patch 滑進一
#張大模板。** 小的那張只要比雜訊多一點結構就有唯一解；patch 小於 cell 反而有利。
#
#前提是大圖拿得到 —— 使用者確認 patch 就是從大圖裁的（同 rcp、同 beam、像素尺寸
#一樣）、大圖每次掃描都有、而 GC **可以跨 lot 共用**（同一支 rcp 掃同一塊 scan
#area）。所以模板**凍進 recipe**（base64 純文字），不是存路徑：存路徑的話圖被搬
#走或換掉，結果會安靜地變，而 recipe 是要交接給別人的東西。
#
#### 我講錯的一件事
#
#我說過「有了大圖，非週期 layout 也能定位」。使用者擋掉：**知道 patch 在大圖的
#哪裡，不等於知道要量哪一塊。** 非週期 layout 沒有「標一次就套用到所有地方」的
#單元，那是 GDS 的事。GC 法的前提是 layout 有週期 —— 這句寫進卡片 help。
#
#### 做了什麼
#
#- `core/algo/template.py`：`build_golden_cell` / `anchor_cell` / `match_patch` /
#  `roi_in_patch` / `encode_cell` / `decode_cell`。
#- `core/steps/roi_template.py`：新卡 **Locate region by template**（Region 段），
#  吐 `match_score` / `match_margin` / `match_structure` / `phase_x` / `phase_y` /
#  `locate_ok`，定不出來退回整張圖 —— 跟投影定位同一個約定。
#- `ui/template_dialog.py`：匯入大圖 → 量週期 → 疊模板 → 看證據 → 寫進 recipe。
#- 測試：`tests/test_roi_template.py`（25）＋`tests/test_ui_f7_12_template.py`（11）。
#
#### 三道閘門，因為分數本身會騙人
#
#比對用 NCC（對亮度／增益免疫，換機台不必重調），但分數單獨看不可信：
#
#1. **一維 layout 不要在另一軸上搜尋** —— 峰的突出程度會被稀釋，「定得出來」被判
#   成「定不出來」。`locate_axis` 讓不重複的那一軸整段吃掉。
#2. **margin 要折回一個週期再算** —— 不折的話相鄰週期的次高峰讓 margin 恆為 0，
#   週期性把自己打敗了。
#3. **先問 patch 自己有沒有東西可比**（`min_structure`）—— 純雜訊對任何模板都能
#   拿到 0.44（門檻 0.3 → 過關）。**沒有任何分數門檻分得出「對得準」與「碰巧」**，
#   因為兩者分數重疊；要問的是另一個問題。實測無結構約 1、有結構 20 以上，
#   20 顆無結構 patch 全數擋下。
#
#### 原點必須錨在地標上
#
#疊出來的 cell 第 0 欄預設是大圖上的任意切點；切點一飄，同一份 recipe 在不同時間
#建的模板會指到不同的地方，而且畫面上看不出來。`anchor_cell()` 旋轉到**最強的
#上升邊**在第 0 欄 —— 用最大正梯度而不是 `abs`，否則一個週期的兩個相反邊界會
#競爭，錨點在兩者之間跳。三個 seed、三個切點鎖進測試。
#
#### 兩個順帶擋掉的安靜失敗
#
#- 一維 layout（垂直條紋）以前在 `py` 量不到週期時直接放棄 —— 而那是最常見的情況。
#  現在兩軸各自判斷，不重複的那一軸取整個影像高度／寬度。
#- 純雜訊上 `estimate_period` 會回一個**看似合理**的週期（實測 py=48、信心 20.3）。
#  信心門檻拉到 40 ——「疊出一個沒有意義的模板」比「說我做不到」糟得多。
#
#### 對話框把判斷材料全部攤開
#
#整條路唯一會**安靜壞掉**的地方是週期估錯：估錯 → 模板糊 → 每顆都對錯 → 畫面上
#沒有錯誤訊息，只有一批看起來很正常、其實量錯位置的數字。所以對話框顯示週期、
#疊了幾格、疊出來長什麼樣、銳利度分數，而且糊掉時**用白話再講一次**後果。
#
#計畫書：`docs/plans/F7-canvas-and-taxonomy.md` §16。
#
#### 還沒做（下一批）
#
#**用當次掃描的大圖對凍在 recipe 裡的 GC 做健檢。** 跨 lot 共用的前提是圖案沒變，
#這個前提會失效（rcp 改過、換 scan area、機台調整），而失效時同樣是安靜的。
#零件都在（`build_golden_cell` + NCC），缺的是 Studio 的一個入口。
#
#---
#
### F7-13 —— 控制項要看得出自己是什麼（試用回饋第四輪 A 組）（2026-07-29）
#
#使用者看了跑起來的畫面：「我先打磨 UI，你覺得目前 UI 有什麼需要改進的？」
#我列了三類，這一輪做的是**不是品味問題**的那一類 —— 三個症狀來自同一種毛病：
#**控制項長得不像它自己**。功能測試抓不到，因為每一項功能都是好的。
#
#### 1. 下拉選單長得像文字框（0 個畫素的箭頭）
#
#`Match on`（擇一）跟 `Name this region`（自由文字）在畫面上一模一樣。
#兇手是一行 QSS：`QComboBox::drop-down { border: 0; ... }` —— styled 的 subcontrol
#要自己提供 down-arrow 圖檔，否則箭頭**完全不畫**，而這個 repo 是純文字的。
#拿掉 `border: 0` 讓它留在 base style 上。
#
#量出來的證據：修之前箭頭區 **0** 個非底色畫素，修之後 20 個，同尺寸的 QLineEdit
#仍然是 0。淺色深色各鎖一次。
#
#### 2. 模板參數不再是文字框
#
#值有六千多個字元、而且是一張影像的內容。文字框讓它「看起來只是還沒填」、
#填了之後變成一片 base64、而且可以被改。新增參數型別 `template`：
#**按鈕就在這一列** + 一行摘要，值唯讀。
#
#按鈕從預覽面板搬回參數列 —— 它是那個參數的值從哪來，不是預覽動作。
#摘要是 `decode_cell` 解出來的，不是另存一個欄位（存旁邊會跟值走散，而走散時
#畫面上完全正常）。
#
#順帶：節點第三行的參數摘要會把模板串成 `template=gc1:iVBOR…`，現在只講
#`template: set`。
#
#### 3. 「這張卡還不能跑」現在看得見
#
#**參數合法 ≠ 設定完成。** 空模板是合法的 str，所以誰都沒話說 —— 但那張卡跑起來
#每一顆都失敗，而使用者是跑完 200 顆才知道的。
#
#新增 `Step.configuration_issues(params)`：卡片自己講缺什麼，而且用**這張卡的話**
#講（要去按哪一顆鈕）。變成 lint error `not-configured`，畫布上的卡片右上角掛
#警示標記，滑鼠停上去講原因。
#
#既有的「每張卡都要有可行組合」測試因此出現一個新分類：路是通的，只是還沒設定完
#—— 不算死路，但**訊息必須指得出路在哪**，那支測試改成這樣要求。
#
#### 4. 按鈕看起來要像按鈕
#
#工具列本來是一排沒有邊框的字 = 讀起來像選單列，而選單列是拉下來的、不是按的。
#現在每顆有自己的表面與邊框，主要動作維持強調色。`First [200]` 加上 ` defects`
#後綴 —— 沒有單位的 200 可以是任何東西。
#
#新測試 `tests/test_ui_controls_readable.py`（9 個）。計畫書 §17。
#
#### 還沒做（使用者清單上的 B / C 組）
#
#B：輸出埠的 `+`（n8n 最核心的操作）、畫布縮放控制、節點副標印關鍵參數。
#C：參數說明只在焦點列展開、空面板給一顆「Open KLARF…」、狀態列的錯誤要有顏色。
#
#---
#
### F7-14 —— 從畫布上就做得完一條 pipeline（B 組）（2026-07-29）
#
#使用者清單裡「n8n 的手感」那三項。看起來像外觀，其實都是功能。
#
#### 1. 輸出埠上的「+」
#
#以前加一張卡要回卡片庫，從 22 張裡自己判斷哪一張接得上。卡片庫的作法是「全部
#列出來、接不上的標 `needs diff`」—— 那個 badge 對不會寫 code 的人沒有動作可做。
#
#**但「接得上」引擎本來就知道。** 埠上的「+」跳出來的清單只列現在就成立的卡，
#依流程階段排序（那是使用者腦中的順序，不是字母序）。
#
#三個決定：**每個輸出埠一顆**（一顆共用的表達不出「我要對 ref 做」）、
#**按的那個埠的影像流會帶進新卡的主要輸入**（不帶的話，從 ref 接出來的 Denoise
#卻做在 test 上 —— 那顆「+」就只是一個比較短的「新增卡片」）、
#**接出來的線是實線**（使用者的動作是意圖，不只是順序）。
#
#「+」畫在埠標籤之外 → `boundingRect` 跟著長。這是同一條不變量的第三次應用
#（F7-8 殘影、F7-9 座標系）：**畫得出去的東西 boundingRect 一定要涵蓋**。
#測試直接斷言每顆「+」的中心都在 boundingRect 裡。
#
#### 2. 縮放控制
#
#滾輪縮放本來就有，但畫面上沒有任何東西說得出這件事 —— 而且滾過頭之後沒有路
#回來：點陣底縮小之後每一格都一樣，使用者不知道自己在哪裡。左下角四顆固定的鈕
#＋百分比，縮放夾在 25%–300%。
#
#### 3. 節點副標
#
#以前印 node_id（`roi_template`）—— 那是 JSON 的鍵，而卡片名字就在上面一行。
#現在印 `吃什麼 → 吐什麼`（`test ref → ref_aligned`）。Region 卡不寫影像流，
#取 `resolve_regions_out()`（`diff → cell`），否則它看起來什麼都不產出。
#重複的卡才把 id 帶出來（`denoise2 · ref → ref`）—— 那時候那個 id 才有意義。
#
#新測試 `tests/test_ui_f7_14_canvas_flow.py`（12 個）。計畫書 §18。
#
#### 還沒做（使用者清單的 C 組）
#
#參數說明只在焦點那一列展開（現在 11 個參數 × 每個 2–3 行灰字＝一定要捲）、
#空面板給一顆「Open KLARF…」、狀態列的錯誤要有顏色。
#
#---
#
### F7-15 —— 畫面上的字要能被讀完（C 組）（2026-07-29）
#
#清單最後一組。三件都不是「功能不對」，是**讀不完／看不到／分不出來**。
#
#### 1. 參數說明收成一行，用到才攤開
#
#11 個參數 × 2–3 行灰字 = 一面牆，一定要捲，而且真正要緊的事（這張卡還沒有模板）
#淹在裡面。現在平常一行（自己算 `elidedText`，不讓 Qt 硬切在字中間），滑鼠移上去
#或欄位拿到焦點才整段攤開。**錯誤永遠攤開** —— 那是他現在最需要讀完的一句話。
#
#`hint_text()` 回的是**全文**不是畫面上那一段：收起來只是畫面上的事。全文也在
#tooltip 裡。不做成「只留 tooltip」是因為那等於把說明藏起來。
#
#Qt 的坑：滑鼠從列的空白處移進**這一列自己的**輸入框時，Qt 先送 Leave 給列、
#再送 Enter 給子元件 —— 照字面處理就是收起來又立刻攤開，看起來閃一下。
#`leaveEvent` 改成直接問游標還在不在這一列的矩形裡。
#
#### 2. 沒資料時最大的那一塊要說得出下一步
#
#以前是一片黑 + 正中央一行 `(no image)` + 角落一行更小的 `(no dataset loaded)`。
#首啟導覽關掉之後就沒有任何東西說得出下一步。現在那塊是 QStackedWidget：
#沒資料 → 「No data loaded yet」＋ **Open KLARF…** ＋ **Try it with sample data**。
#
#### 3. 「沒成功」不能跟「做好了」長得一樣
#
#狀態列是唯一會講「這件事沒成功」的地方，而它跟「Added denoise」用一模一樣的
#灰字，在畫面最左下角。`_status(msg, "error")` 掛屬性，QSS 變紅字粗體。
#
#測試不比對顏色值（會綁死主題），而是**同一句話渲染兩次、只有 level 不同**，
#比畫素 —— 「屬性設了但 QSS 沒規則」正是要擋的情況。哪些訊息算 error 是逐條
#列舉的，不是字串比對（規則比對會把「No results to export yet」也染紅）。
#
#新測試 `tests/test_ui_f7_15_reading_load.py`（9 個）。計畫書 §19。
#
#---
#
### F7-16 —— 四張安全網（2026-07-29）
#
#使用者看完畫面之後問「還有什麼可以改」。我列了三類，這四項排在功能面
#（Feature 面板）前面 —— 因為它們損失的是**已經做完的工作**，不是方便性。
#
#### 1. 復原（Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y）
#
#`RecipeModel` 每個變動之前存一份**整個編輯狀態的快照**，不是反向操作。
#理由：這個 model 有連帶效果（`add_edge` 會重排 `node_order`、`set_param` 會補上
#相依預設值），反向操作要為每一種各寫一次「怎麼倒回去」，漏一個就是「復原之後
#跟原本不一樣」，而那種 bug 使用者看不出來。recipe 很小，存整份是幾十 KB 的事。
#
#**滑桿合併成一步**：拖一次會發幾十次 `set_param`，每次各記一步的話按一次 Ctrl+Z
#只退回一個畫素。鍵在換節點／存檔／復原時清掉 ——「調 A → 做別的 → 再調 A」
#是兩件事。
#
#### 2. 快捷鍵
#
#以前一個都沒有。Ctrl+O / Ctrl+Shift+O / Ctrl+S / Ctrl+R / Ctrl+Z / Ctrl+Shift+Z /
#Ctrl+Y / Ctrl+0 / Ctrl+± / Ctrl+Shift+F / Ctrl+F / Ctrl+←→，全部照作業系統慣例。
#
#坑：`_update_action_states()` 每次 refresh 都會重寫那幾顆的 tooltip，所以
#「建構時附加一次」第一次 refresh 就沒了。改成**設 tooltip 的動作自己補上快捷鍵**。
#
#### 3. 關窗前問一次
#
#`model.dirty` 一直有維護但沒有人讀它。三個答案：存檔／不存／取消，而**存檔失敗
#或在存檔對話框按取消不算可以關**（那是「我改變主意了」）。`_on_save_recipe()`
#從回 None 改成回「真的存下去了嗎」。
#
#`tests/conftest.py` 在測試裡一律關掉這個對話框 —— modal 對話框不會讓 headless
#測試失敗，它會讓測試**永遠停在那裡**，那種卡住最難查。
#
#### 4. 跑到一半可以停
#
#引擎本來就支援（`run_batch` 的 `abort_check`、`TrialWorker.abort()`），只是畫面上
#按不到，使用者唯一的中止方式是關掉整個視窗。進度條旁邊加一顆 Stop。
#
#**已經跑完的留著**（按停止是「不要再等了」，不是「丟掉剛才那五分鐘」），而且
#**不能講 finished** —— 被中止那批的數字描述的是「你叫我停的時候跑到哪」，
#不是整批的結果。差一個字，後面的抓漏率／誤殺率就都建立在錯的前提上。
#
#新測試 `tests/test_ui_f7_16_safety_net.py`（22 個）。計畫書 §20。
#
#### 下一步
#
#Feature 面板（使用者說「右下原 Feature 那一塊還可以拿來利用」）—— 討論中。
#候選：每一列加「這顆在整批裡站哪裡」的分布 + 百分位、點一個特徵就讓它變成
#直方圖/門檻的主角、分數表達式的逐項拆解。資料都已經在 `trial_results` 裡。
#
#---
#
### F7-17 —— 右下角是這張卡自己的儀表（2026-07-30）
#
#使用者：「我一直覺得右下原 Feature 那一塊還可以拿來利用」，而且指出我第一輪提的
#（整批分布、分數拆解）**都比較偏 ADC 面板**，他要的是「每個 card 種類那邊的位置
#可以放什麼」。他是對的 —— 而這個模式 repo 裡已經有了：`roi_profile` 的曲線面板
#不是特例，是**沒有被推廣的通例**。
#
#### 為什麼不是一塊通用面板
#
#`blob_dist_center 11.170` 單獨存在回答不了任何問題。而使用者在問的問題每張卡都
#不一樣：調 Align 要知道「搜尋半徑夠不夠」，調 Denoise 要知道「我有沒有把訊號一起
#磨掉」。挑選原則：**這張卡最常見的失敗模式是什麼，而那個失敗在單顆畫面上看不出來。**
#
#### 這一輪四個（依使用者指定的順序）
#
#1. **`align` 的整批位移散佈圖** ＋ 搜尋半徑方框。對位失敗在單顆上看不出來 ——
#   演算法一定會回一個位移，而 8 是個看起來很正常的數字。真正的失敗是**被半徑
#   截斷**，在散佈圖上就是「點貼在框邊」，而且照做得出來（把半徑調大）。
#2. **Enhance 九張卡共用的 before/after 直方圖 + 削平計數**。Enhance 的失敗是安靜
#   的：「看起來變乾淨了」但六成畫素被壓到黑白兩端，而後面每張量測卡都吃這結果。
#3. **五張量測卡的整批分布 + 這一顆站在哪**。只列**這張卡自己**的特徵（含
#   output_prefix）—— 整份 feature 表是 ADC 的事。擠成一根柱子 = 沒有鑑別力。
#4. **`load_patch` 的 page → stream 對應**。這是全專案第一條待廠內驗證的假設；
#   以前只能靠另外跑 `fab_probe`，現在載入第一份真資料就看得到（兩頁平均灰階差
#   8 以上直接警告）。
#
#### 機制（決定它會不會變成一坨 if/else）
#
#依 `Step.key` 註冊，沒註冊的用原本的特徵表 → **加新卡不必動 inspectors.py**。
#面板畫的是引擎算的那一份（`ctx.meta` 或 `trial_results`），UI 不重算。
#沒資料時要說得出為什麼沒有。
#
#### before/after 需要引擎配合，而它是選配的
#
#Enhance 卡就地改寫同一條流，跑完「之前」就沒了。`Context.track_changes`：
#覆寫既有流時把前後各壓成 48 格直方圖 + 削平比例放進 `ctx.meta["stream_change"]`。
#**預設關，只有預覽打開** —— 批次一萬顆時那份資料沒有人看。
#
#### 三個踩到的
#
#- **直方圖高度用平方根**：削平在兩端堆出兩根極高的柱子，線性刻度下其餘分布被壓
#  成貼底的一條線，而那正是要比較的形狀。
#- **「這一顆」會落在整批範圍外，那是正常的**（改參數後預覽即時重算、整批還是舊
#  的）。夾回邊界並畫成箭頭，不夾會畫到面板外蓋到文字。
#- **`drawPolygon(QPointF, QPointF, QPointF)` 在 PySide6 直接 segfault**（不是丟
#  例外，是整個行程掛掉）——要傳 `QPolygonF`。
#
#順手修掉一個潛在地雷：暗色盤裡 `accent_border` 的值是 `"#2f4straight"`（F7-2 留下
#的佔位字串），靠 70 行後的一句覆寫救著。已經就地改成真值並拿掉那句覆寫。
#
#新測試 `tests/test_ui_f7_17_inspectors.py`（25 個）。計畫書 §21。
#
#### 還沒做（同一個機制）
#
#`roi_template` 的比對曲面與三道閘門、`blob_segment` 的 label map、`subtract` 的
#背景殘差、`roi_snr` 的分子分母分解、Region 卡常駐的「框畫在前 N 顆縮圖上」，
#以及跨卡片的頁尾「這張卡在這批花了多少時間」。`roi_profile` 的曲線面板也該收進
#這個機制 —— 現在是另一條路，兩條並存會腐爛。
#
#### F7-17 第二批：Region 的兩張卡（2026-07-30）
#
#**`roi_profile` 的曲線面板收進儀表機制。** 它 F7-11 就做好了，但直接掛在預覽面板
#上 —— 一條跟儀表平行的路。兩條並存的下場是加新面板的人不知道走哪一條，然後兩邊
#各長一半。畫的還是同一個元件，只是換地方住；`profile_panel` 這個名字保留，
#選到別的卡時回**空的替身**不是 None（呼叫端不必到處寫 if is None）。
#
#**`roi_template` 的三道閘門。** 定位失敗只講「退回整張圖」，但三個原因的處置
#完全不同：match 低＝模板不對；certainty 低＝對得上的位置不只一個；
#**structure 低＝這張 patch 根本沒東西可比，那不是參數問題，退回整張圖就是對的
#答案**。分不出來的話使用者會一直調前兩個門檻，一路調低到它開始亂放框。
#
#面板是三根柱子，每根畫著**它自己的門檻線** —— 沒有那條線，柱子的長度沒有意義。
#
#測試加到 34 個。計畫書 §21.6。
#
#F 650a5d7c8bc6db42eed4054174823bfcfceb7eae 7 adept/__init__.py
#"""ADEPT — flexible multi-step ADC for semiconductor inspection.
#
#讀 EBI patch（test+ref）或 RSEM 單張影像 + 對應 KLARF，
#以「步驟卡片組 pipeline」把想法變成算法，對每顆 defect 算分、寫回 KLARF。
#"""
#__version__ = "0.1.0.dev0"  # M0: vendored core library
#
#F 2f6c872448859787dbe6cfba4ef6c2e819d576da 364 adept/__main__.py
## ADEPT CLI — authored 2026-07-27 (M1).
#"""ADEPT 指令列介面。
#
#用法：
#    python -m adept steps                          # 列出所有卡片
#    python -m adept validate RECIPE [--kind K]     # recipe 健檢（lint）
#    python -m adept run RECIPE KLARF [--tiff T] [--out r.json] [--csv r.csv] [--limit N]
#
#合成測試資料：``python tools/make_sample.py OUT_DIR``（見 tools/）。
#"""
#from __future__ import annotations
#
#import argparse
#import csv
#import json
#import sys
#from typing import List, Optional
#
#
#def _cmd_steps(_args: argparse.Namespace) -> int:
#    import adept.core.steps  # noqa: F401 — 觸發註冊
#    from adept.core.pipeline import list_steps
#
#    names = {"image": "影像段 IMAGE", "algo": "算法段 ALGO", "adc": "判定段 ADC"}
#    for cat in ("image", "algo", "adc"):
#        cards = list_steps(cat)
#        if not cards:
#            continue
#        print(f"\n== {names[cat]} ==")
#        for s in cards:
#            flag = "（需要 ref）" if s.requires_ref else ""
#            print(f"  {s.key:<16} {s.label}{flag} — {s.help}")
#            for p in s.params:
#                print(f"      · {p.name} ({p.type}, 預設 {p.default!r}) — {p.help}")
#    return 0
#
#
#def _load_recipe(path: str):
#    from adept.core.pipeline import Recipe
#
#    try:
#        return Recipe.load(path)
#    except Exception as exc:  # noqa: BLE001 — CLI 邊界
#        print(f"[錯誤] 無法載入 recipe：{exc}", file=sys.stderr)
#        return None
#
#
#def _print_issues(issues) -> bool:
#    """列印 lint 結果；回傳是否有 error 等級。"""
#    has_error = False
#    for it in issues:
#        mark = "✗" if it.level == "error" else "△"
#        has_error = has_error or it.level == "error"
#        node = f" @{it.node_id}" if it.node_id else ""
#        print(f"  {mark} [{it.code}]{node} {it.title} — {it.detail}")
#    if not issues:
#        print("  ✓ 無問題")
#    return has_error
#
#
#def _cmd_validate(args: argparse.Namespace) -> int:
#    import adept.core.steps  # noqa: F401
#    from adept.core.pipeline import validate
#
#    recipe = _load_recipe(args.recipe)
#    if recipe is None:
#        return 2
#    kinds = [args.kind] if args.kind else sorted(recipe.routes)
#    bad = False
#    for kind in kinds:
#        print(f"\n-- route: {kind} --")
#        bad = _print_issues(validate(recipe, kind=kind)) or bad
#    return 1 if bad else 0
#
#
#def _cmd_run(args: argparse.Namespace) -> int:
#    import time
#
#    import adept.core.steps  # noqa: F401
#    from adept.core.ingest.dataset import load_dataset
#    from adept.core.pipeline import run_batch, validate
#
#    recipe = _load_recipe(args.recipe)
#    if recipe is None:
#        return 2
#
#    ds = load_dataset(args.klarf, tiff_path=args.tiff)
#    print(f"資料集：kind={ds.kind}，{len(ds.items)} 顆 defect")
#    for w in ds.warnings:
#        print(f"  △ {w}")
#    if ds.kind not in recipe.routes:
#        print(f"[錯誤] recipe 沒有 '{ds.kind}' 的 route（有：{sorted(recipe.routes)}）", file=sys.stderr)
#        return 2
#
#    print(f"\nRecipe 健檢（{ds.kind}）：")
#    if _print_issues(validate(recipe, kind=ds.kind)):
#        print("[錯誤] recipe 有 error 等級問題，請先修正。", file=sys.stderr)
#        return 1
#
#    n_total = min(len(ds.items), args.limit) if args.limit else len(ds.items)
#
#    def _progress(i: int, n: int, res) -> None:
#        if (i + 1) % 50 == 0 or (i + 1) == n:
#            print(f"  … {i + 1}/{n}", flush=True)
#
#    print(f"\n執行 {n_total} 顆（workers={args.workers or 'auto'}"
#          f"{'，cache=' + args.cache if args.cache else ''}）：")
#    t0 = time.perf_counter()
#    payload = run_batch(recipe, ds, workers=args.workers, cache_dir=args.cache,
#                        progress=_progress, limit=args.limit)
#    elapsed = time.perf_counter() - t0
#
#    ok = [r for r in payload if r.get("ok")]
#    fail = [r for r in payload if not r.get("ok")]
#    scores = [r.get("score") for r in ok if r.get("score") is not None]
#    per = (elapsed / max(len(payload), 1)) * 1000
#    print(f"\n完成：{len(ok)} 成功 / {len(fail)} 失敗 · {elapsed:.1f}s（{per:.1f} ms/顆）")
#    if scores:
#        import statistics
#
#        print(
#            f"score：min {min(scores):.3f} · median {statistics.median(scores):.3f} · max {max(scores):.3f}"
#        )
#        bins: dict = {}
#        for r in ok:
#            bins[r.get("bin")] = bins.get(r.get("bin"), 0) + 1
#        print("bin 分佈：" + " · ".join(f"bin {b}={c}" for b, c in sorted(bins.items())))
#    for r in fail[:5]:
#        print(f"  ✗ {r.get('defect_id')}: {r.get('error')}")
#
#    if args.db:
#        from adept.core.store import RunStore
#
#        with RunStore(args.db) as store:
#            run_id = store.save_run(recipe, payload, klarf_path=str(args.klarf),
#                                    dataset_kind=ds.kind, notes=args.notes or "")
#        print(f"→ 已存入批次歷史：run_id={run_id}（{args.db}）")
#    if args.out:
#        with open(args.out, "w", encoding="utf-8") as f:
#            json.dump(payload, f, ensure_ascii=False, indent=2)
#        print(f"→ JSON：{args.out}")
#    if args.csv:
#        feat_keys: List[str] = sorted({k for r in payload for k in r.get("features", {})})
#        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
#            w = csv.writer(f)
#            w.writerow(["defect_id", "ok", "error", "score", "bin"] + feat_keys)
#            for r in payload:
#                feats = r.get("features", {})
#                w.writerow(
#                    [r["defect_id"], r["ok"], r.get("error") or "", r.get("score"), r.get("bin")]
#                    + [feats.get(k) for k in feat_keys]
#                )
#        print(f"→ CSV：{args.csv}")
#    return 0
#
#
#def _cmd_runs(args: argparse.Namespace) -> int:
#    from adept.core.store import RunStore
#
#    with RunStore(args.db) as store:
#        rows = store.list_runs()
#    if not rows:
#        print("（尚無批次歷史）")
#        return 0
#    for r in rows:
#        print(f"{r['run_id']}  {r['created_utc']}  recipe={r['recipe_id']}  "
#              f"kind={r['dataset_kind']}  n={r['n_total']}（ok {r['n_ok']} / fail {r['n_fail']}）"
#              f"{'  ' + r['notes'] if r.get('notes') else ''}")
#    return 0
#
#
#def _cmd_rescore(args: argparse.Namespace) -> int:
#    from adept.core.store import RunStore, rescore
#
#    bins = None
#    if args.bins:
#        try:
#            lo, hi = (int(x) for x in args.bins.split(","))
#            bins = {"below": lo, "above": hi}
#        except ValueError:
#            print("[錯誤] --bins 格式：below,above（例：0,1）", file=sys.stderr)
#            return 2
#    with RunStore(args.db) as store:
#        try:
#            summary = rescore(store, args.run_id, expr=args.expr,
#                              threshold=args.threshold, bins=bins,
#                              save_as=(True if args.save else None), notes=args.notes or "")
#        except KeyError as e:
#            print(f"[錯誤] {e}", file=sys.stderr)
#            return 2
#    print(f"rescore {summary['run_id']}：n={summary['n']}，錯誤 {summary['n_errors']}，"
#          f"耗時 {summary['elapsed_s']:.2f}s")
#    if summary.get("bin_counts"):
#        print("bin 分佈：" + " · ".join(f"bin {b}={c}" for b, c in sorted(summary["bin_counts"].items())))
#    if summary.get("score_min") is not None:
#        print(f"score：min {summary['score_min']:.3f} · median {summary['score_median']:.3f} · "
#              f"max {summary['score_max']:.3f}")
#    if summary.get("saved_run_id"):
#        print(f"→ 已另存為新 run：{summary['saved_run_id']}")
#    return 0
#
#
#def _cmd_export(args: argparse.Namespace) -> int:
#    """把批次歷史裡的一次執行結果輸出：寫回 KLARF / 報表。"""
#    import json
#
#    import adept.core.steps  # noqa: F401
#    from adept.core.export import (
#        ExportError, apply_writeback, plan_writeback, summarize,
#        write_csv, write_excel,
#    )
#    from adept.core.ingest import klarf_core
#    from adept.core.store import RunStore
#
#    with RunStore(args.db) as store:
#        try:
#            run = store.get_run(args.run_id)
#            results = list(store.iter_results(args.run_id))
#        except Exception as exc:  # noqa: BLE001 — CLI 邊界
#            print(f"[錯誤] 讀不到 run '{args.run_id}'：{exc}", file=sys.stderr)
#            return 2
#    print(f"run {args.run_id}：{len(results)} 筆結果"
#          f"（recipe={run.get('recipe_id')}，kind={run.get('dataset_kind')}）")
#
#    gt = None
#    if args.ground_truth:
#        with open(args.ground_truth, encoding="utf-8") as f:
#            gt = json.load(f)
#    s = summarize(results, ground_truth=gt)
#    print(f"成功 {s.get('n_ok')} / 失敗 {s.get('n_fail')}；"
#          f"bin 分佈 " + " · ".join(f"bin {b}={c}"
#                                   for b, c in sorted((s.get('bin_counts') or {}).items(),
#                                                      key=lambda kv: str(kv[0]))))
#    g = s.get("ground_truth") or {}
#    if g.get("n_evaluated"):
#        print(f"對照 ground truth（{g['n_evaluated']} 顆）："
#              f"正確率 {g.get('accuracy', 0):.1%}　"
#              f"抓漏率 {g.get('miss_rate', 0):.1%}（漏抓 {g.get('fn', 0)} 顆真缺陷）　"
#              f"誤殺率 {g.get('false_alarm_rate', 0):.1%}（誤判 {g.get('fp', 0)} 顆假點）")
#
#    if args.csv:
#        print(f"→ CSV：{write_csv(results, args.csv)}")
#    if args.excel:
#        try:
#            print(f"→ Excel：{write_excel(results, args.excel, ground_truth=gt)}")
#        except ExportError as exc:
#            print(f"[錯誤] {exc}", file=sys.stderr)
#            return 2
#
#    if args.klarf_out or args.dry_run:
#        src = args.klarf or run.get("klarf_path")
#        if not src:
#            print("[錯誤] 沒有來源 KLARF；請用 --klarf 指定。", file=sys.stderr)
#            return 2
#        doc = klarf_core.load(src)
#        opts = {}
#        if args.mode == "inplace":
#            opts = {"class_col": args.class_col, "bin_col": args.bin_col,
#                    "size_col": args.size_col}
#            opts = {k: v for k, v in opts.items() if v}
#        elif args.mode == "topn":
#            opts = {"n": args.top_n, "min_score": args.min_score}
#        try:
#            if args.dry_run:
#                plan = plan_writeback(doc, results, args.mode, **opts)
#            else:
#                plan = apply_writeback(doc, results, args.mode, args.klarf_out, **opts)
#        except ExportError as exc:
#            print(f"[錯誤] {exc}", file=sys.stderr)
#            return 2
#        print(f"\n寫回模式：{plan.mode}{'（預覽，未寫檔）' if args.dry_run else ''}")
#        print(f"  會改動 {plan.n_rows_changed} 列；輸出 {plan.n_rows_out} 列")
#        if plan.columns_touched:
#            print(f"  動到欄位：{', '.join(plan.columns_touched)}")
#        if plan.columns_added:
#            print(f"  新增欄位：{', '.join(plan.columns_added)}")
#        for note in plan.notes:
#            print(f"  · {note}")
#        for it in plan.issues:
#            mark = {"error": "✗", "warning": "△"}.get(getattr(it, "level", ""), "·")
#            print(f"  {mark} [{getattr(it, 'code', '?')}] {getattr(it, 'title', it)}")
#        if not args.dry_run:
#            print(f"→ KLARF：{args.klarf_out}")
#    return 0
#
#
#def _cmd_gui(_args: argparse.Namespace) -> int:
#    """開 Studio。PySide6 在此 lazy import —— core/CLI 本身不依賴 Qt。"""
#    try:
#        from adept.ui.app import main as gui_main
#    except ImportError as exc:
#        print(f"[錯誤] 無法載入圖形介面（需要 PySide6）：{exc}\n"
#              f"       安裝：pip install PySide6", file=sys.stderr)
#        return 2
#    return gui_main([])
#
#
#def main(argv: Optional[List[str]] = None) -> int:
#    ap = argparse.ArgumentParser(
#        prog="adept",
#        description="ADEPT — 把想法變算法的 ADC 工具",
#    )
#    sub = ap.add_subparsers(dest="cmd", required=True)
#
#    sub.add_parser("gui", help="開啟 Studio 視覺化介面").set_defaults(func=_cmd_gui)
#    sub.add_parser("steps", help="列出所有已註冊卡片").set_defaults(func=_cmd_steps)
#
#    p_val = sub.add_parser("validate", help="Recipe 健檢（lint）")
#    p_val.add_argument("recipe")
#    p_val.add_argument("--kind", default=None, help="只檢查特定資料型別（ebi_patch/rsem）")
#    p_val.set_defaults(func=_cmd_validate)
#
#    p_run = sub.add_parser("run", help="對一份 KLARF(+TIFF) 跑 recipe")
#    p_run.add_argument("recipe")
#    p_run.add_argument("klarf")
#    p_run.add_argument("--tiff", default=None, help="patch TIFF 路徑（預設自動尋找）")
#    p_run.add_argument("--out", default=None, help="輸出 JSON 路徑")
#    p_run.add_argument("--csv", default=None, help="輸出 CSV 路徑（feature vector）")
#    p_run.add_argument("--limit", type=int, default=None, help="只跑前 N 顆（試跑）")
#    p_run.add_argument("--workers", type=int, default=None, help="平行 worker 數（預設=CPU 核心數；1=單進程）")
#    p_run.add_argument("--cache", default=None, help="影像段快取資料夾（改算法段參數重跑會大幅加速）")
#    p_run.add_argument("--db", default=None, help="存入批次歷史 SQLite（例：~/.adept/runs.db）")
#    p_run.add_argument("--notes", default=None, help="批次備註")
#    p_run.set_defaults(func=_cmd_run)
#
#    p_runs = sub.add_parser("runs", help="列出批次歷史")
#    p_runs.add_argument("--db", required=True, help="批次歷史 SQLite 路徑")
#    p_runs.set_defaults(func=_cmd_runs)
#
#    p_ex = sub.add_parser("export", help="輸出：寫回 KLARF / CSV / Excel 報表")
#    p_ex.add_argument("run_id")
#    p_ex.add_argument("--db", required=True, help="批次歷史 SQLite 路徑")
#    p_ex.add_argument("--mode", choices=["inplace", "annotate", "topn"], default="annotate",
#                      help="寫回模式：inplace=就地改欄（無損）／annotate=另存含分數欄／topn=只留前 N 名")
#    p_ex.add_argument("--klarf", default=None, help="來源 KLARF（預設用 run 紀錄裡的路徑）")
#    p_ex.add_argument("--klarf-out", default=None, help="輸出 KLARF 路徑")
#    p_ex.add_argument("--dry-run", action="store_true", help="只預覽會改什麼，不寫檔")
#    p_ex.add_argument("--class-col", default=None, help="inplace：bin 寫進哪個分類欄（例 CLASSNUMBER）")
#    p_ex.add_argument("--bin-col", default=None, help="inplace：bin 寫進哪個 bin 欄（例 ROUGHBINNUMBER）")
#    p_ex.add_argument("--size-col", default=None, help="inplace：CD 寫進哪個尺寸欄（例 DSIZE）")
#    p_ex.add_argument("--top-n", type=int, default=0, help="topn：取前幾名（0=改用 --min-score）")
#    p_ex.add_argument("--min-score", type=float, default=0.0, help="topn：分數門檻")
#    p_ex.add_argument("--csv", default=None, help="輸出 feature vector CSV")
#    p_ex.add_argument("--excel", default=None, help="輸出 Excel 報表（需要 openpyxl）")
#    p_ex.add_argument("--ground-truth", default=None, help="ground_truth.json（有的話會算正確率/抓漏率）")
#    p_ex.set_defaults(func=_cmd_export)
#
#    p_rs = sub.add_parser("rescore", help="改分數表達式/門檻重算（不重跑影像，秒級）")
#    p_rs.add_argument("run_id")
#    p_rs.add_argument("--db", required=True, help="批次歷史 SQLite 路徑")
#    p_rs.add_argument("--expr", default=None, help="新的分數表達式（不給=沿用）")
#    p_rs.add_argument("--threshold", type=float, default=None, help="新門檻")
#    p_rs.add_argument("--bins", default=None, help="below,above（例：0,1）")
#    p_rs.add_argument("--save", action="store_true", help="另存為新 run")
#    p_rs.add_argument("--notes", default=None, help="備註")
#    p_rs.set_defaults(func=_cmd_rescore)
#
#    args = ap.parse_args(argv)
#    return args.func(args)
#
#
#if __name__ == "__main__":
#    raise SystemExit(main())
#
#F 8a51dfe499b3a9d81434c8a202f2d17c24b71c74 2 adept/core/__init__.py
#"""ADEPT core — 純運算層，禁止任何 Qt import（測試會檢查）。"""
#
#F bb867d35f598c29094fc4532235e51b959a694fe 28 adept/core/algo/__init__.py
#"""演算法模組（純 numpy/cv2，零 Qt）— vendored from KLIP/GLAS/MMH/PEAR/CPE/Fusi³."""
#from __future__ import annotations
#
#from .normalize import (
#    normalize_image, percentile_range, normalize_image_with_range,
#    percentile_range_glv_masked,
#)
#from .histmatch import (
#    match_histogram_exact, match_histogram_linear, match_histogram_percentile,
#    MATCH_FN, compute_histogram, image_stats,
#)
#from .align import (
#    AlignResult, apply_alignment, calculate_alignment, calculate_alignment_robust,
#    ncc_score, parabola_subpx, template_align_nm,
#)
#from .snr import (
#    snr_signed, roi_snr, RoiSnrResult, compute_snr_map, SnrMapResult,
#    center_gaussian_mask,
#)
#from .blob import DefectROI, segment_defects
#from .roi import NamedROI, ROIStats, MultiROISet, pixel_rect_to_norm
#from .glv import glv_value, glv_stats, default_metrics, roi_patch, group_snr, pixel_hist, summarize
#from .stats import group_outliers, cohens_d, attribute_separability
#from .period import estimate_period, PeriodResult
#from .golden import tile_coords, stack_cells, ghosting_score, refine_period, candidate_periods
#from .quality import check_lap_quality, compute_quality, DEFAULT_LAP_THRESHOLD
#from . import subpixel
#
#F e86b06ccad3b3981eb4a162d0a99f968fc4fade3 687 adept/core/algo/align.py
## ---------------------------------------------------------------------------
## Vendored into ADEPT on 2026-07-27.
## Source projects/files:
##   - Perspective-Combination (Fusi3): perscomb/core/perspective_combine.py
##       (_apply_alignment, _alignment_overlap_slices, _ncc_score,
##        _calculate_alignment_scores, _calculate_alignment_ncc,
##        _calculate_alignment_ecc, _calculate_alignment_template,
##        _calculate_alignment)
##   - Perspective-Combination (Fusi3): perscomb/core/ebeam_snr.py
##       (AlignResult, _preprocess_for_align, calculate_alignment_robust)
##   - GLAS: glas/core/fine_align.py
##       (fine_align_one, _parabola_subpx)
## Adaptations:
##   - Leading underscores dropped from vendored public helper names
##     (apply_alignment, alignment_overlap_slices, ncc_score, parabola_subpx);
##     backend implementations stay private, dispatched via calculate_alignment.
##   - Normalization helpers imported from adept.core.algo.normalize instead
##     of module-local copies.
##   - SIGN FIX in the ECC backend: cv2.findTransformECC warps the input image
##     with WARP_INVERSE_MAP internally, i.e. warped(x) = target(x + t), so the
##     converged translation t equals (+dx, +dy) in this module's convention.
##     The original code seeded the warp with (-dx, -dy) and returned
##     dx = -t.x / dy = -t.y, which produced a shift with the OPPOSITE sign of
##     the phase/ncc/template backends (verified empirically on planted
##     shifts). The vendored version seeds with (+dx, +dy) and returns
##     dx = +t.x / dy = +t.y so all backends share one convention.
##   - Flat-image guard added: calculate_alignment and
##     calculate_alignment_robust return a zero-shift 'fail' AlignResult when
##     either input is constant (std < 1e-9); previously cv2.phaseCorrelate on
##     an all-zero edge map could yield NaN and crash int(round(...)).
##   - GLAS fine_align_one renamed template_align_nm; its "cv2 is None" import
##     guard removed (cv2 is a hard dependency of this package).
##   - Explicit .astype(np.float32) added before cv2.warpAffine in the scoring
##     paths (normalize_image upcasts to float64 via np.percentile).
##   - Algorithm behavior otherwise unchanged.
## ---------------------------------------------------------------------------
#"""Image-to-image translation alignment backends for SEM defect imaging.
#
#(dx, dy) SIGN CONVENTION (all ``calculate_alignment*`` backends)
#----------------------------------------------------------------
#The returned shift is the displacement of **target relative to base**, in
#image pixel coordinates with +x = right (columns) and +y = down (rows):
#
#    target(x, y) == base(x - dx, y - dy)
#
#i.e. if the target's content appears ``dx`` pixels to the right of and ``dy``
#pixels below the same content in the base image, every backend ("phase",
#"hybrid", "ncc", "ecc", "template") returns positive ``(dx, dy)``.
#Consequently ``apply_alignment(target, dx, dy)`` shifts the target content
#back by ``(-dx, -dy)`` and registers it onto the base image.
#
#Exception: :func:`template_align_nm` (vendored from GLAS) does NOT return an
#image-space (dx, dy); it returns a GDS overlay *anchor correction* in
#nanometres, where the x component is negated (GDS anchor x decreases to move
#the overlay right) and y follows the image-down direction. See its docstring.
#"""
#from __future__ import annotations
#
#from dataclasses import dataclass
#from typing import Tuple
#
#import cv2
#import numpy as np
#
#from .normalize import normalize_image
#
#
#@dataclass
#class AlignResult:
#    """Result of robust alignment process."""
#    dx: int
#    dy: int
#    score_phase: float
#    score_ncc: float
#    score_residual: float
#    final_score: float
#    status: str  # 'ok', 'warn', 'fail'
#    method: str  # 'phase', 'ncc', 'fallback'
#    # Sub-pixel precision offsets (default to integer values for backward compat)
#    dx_subpixel: float = 0.0
#    dy_subpixel: float = 0.0
#
#
#def apply_alignment(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
#    """Apply sub-pixel translation to image using affine warp (INTER_LINEAR).
#
#    Shifts the image content by (-dx, -dy): given ``target(x, y) == base(x -
#    dx, y - dy)``, ``apply_alignment(target, dx, dy)`` registers the target
#    onto the base.
#    """
#    if image is None:
#        return None
#
#    h, w = image.shape[:2]
#    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
#    aligned = cv2.warpAffine(image, M, (w, h),
#                             flags=cv2.INTER_LINEAR,
#                             borderMode=cv2.BORDER_REPLICATE)
#    return aligned
#
#
#def alignment_overlap_slices(shape: Tuple[int, int], dx: int, dy: int) -> Tuple[slice, slice, slice, slice]:
#    """Return slices for overlapping regions given a shift.
#
#    Returns ``(base_y, base_x, target_y, target_x)`` such that
#    ``base[base_y, base_x]`` and ``target[target_y, target_x]`` cover the same
#    scene content when the target is displaced by ``(dx, dy)`` relative to the
#    base (see module docstring for the sign convention).
#    """
#    h, w = shape
#    if dx >= 0:
#        base_x = slice(0, w - dx)
#        target_x = slice(dx, w)
#    else:
#        base_x = slice(-dx, w)
#        target_x = slice(0, w + dx)
#
#    if dy >= 0:
#        base_y = slice(0, h - dy)
#        target_y = slice(dy, h)
#    else:
#        base_y = slice(-dy, h)
#        target_y = slice(0, h + dy)
#
#    return base_y, base_x, target_y, target_x
#
#
#def ncc_score(a: np.ndarray, b: np.ndarray) -> float:
#    """Compute normalized cross-correlation score between two same-shape arrays."""
#    a_mean = float(np.mean(a))
#    b_mean = float(np.mean(b))
#    a_z = a - a_mean
#    b_z = b - b_mean
#    denom = float(np.sqrt(np.sum(a_z ** 2) * np.sum(b_z ** 2))) + 1e-6
#    return float(np.sum(a_z * b_z) / denom)
#
#
#def _calculate_alignment_scores(
#    base: np.ndarray,
#    target: np.ndarray,
#    dx: int,
#    dy: int,
#    phase_score: float = 0.0,
#    method: str = "phase"
#) -> Tuple[float, float, float]:
#    """Calculate NCC, residual, and final score for a given shift."""
#    base_norm = normalize_image(base.astype(np.float32))
#    target_norm = normalize_image(target.astype(np.float32))
#    aligned_target = apply_alignment(target_norm.astype(np.float32), dx, dy)
#    residual = float(np.mean(np.abs(base_norm - aligned_target)))
#    score_residual = max(0.0, 1.0 - residual * 2.0)
#
#    by, bx, ty, tx = alignment_overlap_slices(base_norm.shape[:2], dx, dy)
#    if by.stop <= by.start or bx.stop <= bx.start:
#        score_ncc = 0.0
#    else:
#        score_ncc = (ncc_score(base_norm[by, bx], target_norm[ty, tx]) + 1.0) / 2.0
#
#    if method == "ncc":
#        final_score = (0.6 * score_ncc + 0.4 * score_residual) * 100.0
#    else:
#        final_score = (0.4 * phase_score + 0.6 * score_residual) * 100.0
#
#    return score_ncc, score_residual, final_score
#
#
## ---------------------------------------------------------------------------
## Phase-correlation backend (vendored from ebeam_snr.py)
## ---------------------------------------------------------------------------
#
#def _preprocess_for_align(img: np.ndarray) -> np.ndarray:
#    """Preprocess image for alignment (Robust Norm + Sobel)."""
#    if img is None:
#        return None
#
#    img_f = img.astype(np.float32)
#    # Robust normalization (5th-95th percentile)
#    p5, p95 = np.percentile(img_f, [5, 95])
#    rng = p95 - p5
#    if rng < 1e-6:
#        rng = 1.0
#    img_n = np.clip((img_f - p5) / rng, 0, 1)
#
#    # Sobel Edge Detection
#    # Ensure explicit float32 for OpenCV compatibility
#    gx = cv2.Sobel(img_n.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
#    gy = cv2.Sobel(img_n.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
#    mag = cv2.magnitude(gx, gy)
#
#    # Normalize magnitude
#    mmax = mag.max()
#    if mmax > 1e-6:
#        mag /= mmax
#
#    return mag
#
#
#def _is_flat(img: np.ndarray) -> bool:
#    """True when the image is constant (no signal for any alignment backend)."""
#    return float(np.std(img.astype(np.float32))) < 1e-9
#
#
#def calculate_alignment_robust(
#    base: np.ndarray,
#    target: np.ndarray,
#    search_radius: int = 40
#) -> AlignResult:
#    """Layered robust alignment strategy.
#
#    Strategy:
#    1. Preprocess (Edge map) to ignore brightness diffs.
#    2. Phase Correlation (Layer 1) for fast translation estimate.
#    3. Verification & Grading.
#    """
#    if base is None or target is None:
#        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
#
#    if _is_flat(base) or _is_flat(target):
#        # Flat-image guard: phase correlation on a zero edge map is undefined.
#        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
#
#    h, w = base.shape[:2]
#
#    # Performance guard for very large images:
#    # phaseCorrelate runs FFT internally, so runtime grows quickly with image size.
#    # Downsample to a working resolution, then scale sub-pixel shift back.
#    max_dim = max(h, w)
#    align_max_dim = 2048
#    scale_x = 1.0
#    scale_y = 1.0
#    if max_dim > align_max_dim:
#        down = align_max_dim / float(max_dim)
#        work_w = max(64, int(round(w * down)))
#        work_h = max(64, int(round(h * down)))
#        scale_x = w / float(work_w)
#        scale_y = h / float(work_h)
#    else:
#        work_w = w
#        work_h = h
#
#    # 1. Preprocessing
#    base_edge = _preprocess_for_align(base)
#    target_edge = _preprocess_for_align(target)
#    if (work_w, work_h) != (w, h):
#        base_edge = cv2.resize(base_edge, (work_w, work_h), interpolation=cv2.INTER_AREA)
#        target_edge = cv2.resize(target_edge, (work_w, work_h), interpolation=cv2.INTER_AREA)
#
#    # 2. Phase Correlation (Layer 1)
#    # Create Hanning window to reduce edge effects
#    hann = cv2.createHanningWindow((work_w, work_h), cv2.CV_32F)
#    (dx_p, dy_p), response_p = cv2.phaseCorrelate(base_edge, target_edge, window=hann)
#
#    # Convert working-resolution shift back to original coordinates.
#    dx_p *= scale_x
#    dy_p *= scale_y
#
#    # Convert phase shift (target->base)
#    # cv2.phaseCorrelate returns shift of src2 relative to src1.
#    # So dx, dy is the shift.
#
#    # 3. Residual Verification
#    # Shift target edge back by (-dx, -dy)
#    M = np.float32([[1, 0, -(dx_p / scale_x)], [0, 1, -(dy_p / scale_y)]])
#    aligned_edge = cv2.warpAffine(target_edge, M, (work_w, work_h), flags=cv2.INTER_LINEAR)
#
#    # Calculate residual (Difference in overlap area)
#    diff = np.abs(base_edge - aligned_edge)
#    # Ignore border regions affected by shift
#    border = 5 + int(max(abs(dx_p / scale_x), abs(dy_p / scale_y)))
#    if border < work_h // 2 and border < work_w // 2:
#        valid_diff = diff[border:-border, border:-border]
#    else:
#        valid_diff = diff
#
#    residual_mean = float(np.mean(valid_diff))
#    score_residual = max(0.0, 1.0 - residual_mean * 2.0)  # Heuristic scaling
#
#    # 4. Composite Score
#    # Weights: Phase=0.4, NCC/Legacy=0.0 (using residual instead), Residual=0.6
#    final_score = (0.4 * response_p + 0.6 * score_residual) * 100.0
#
#    # 5. Grading
#    status = 'ok'
#    if final_score < 75:
#        status = 'warn'
#    if final_score < 55:
#        status = 'fail'
#
#    # Limit shift to search radius
#    if abs(dx_p) > search_radius or abs(dy_p) > search_radius:
#        # If phase corr says huge shift, it might be wrong (or just huge).
#        # Report it but warn.
#        status = 'warn'
#
#    return AlignResult(
#        dx=int(round(dx_p)),
#        dy=int(round(dy_p)),
#        score_phase=float(response_p),
#        score_ncc=0.0,  # Not computed yet
#        score_residual=score_residual,
#        final_score=final_score,
#        status=status,
#        method='phase',
#        dx_subpixel=float(dx_p),
#        dy_subpixel=float(dy_p),
#    )
#
#
## ---------------------------------------------------------------------------
## NCC backend
## ---------------------------------------------------------------------------
#
#def _calculate_alignment_ncc(
#    base: np.ndarray,
#    target: np.ndarray,
#    search_radius: int = 40
#) -> AlignResult:
#    """NCC alignment with coarse-to-fine search for efficiency.
#
#    Uses a two-stage approach:
#    1. Coarse search with step=4 over full radius
#    2. Fine search with step=1 in ±4 pixel neighborhood around best
#
#    This reduces computation from ~6561 to ~400 NCC evaluations.
#    """
#    if base is None or target is None:
#        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
#
#    base_f = normalize_image(base.astype(np.float32))
#    target_f = normalize_image(target.astype(np.float32))
#    h, w = base_f.shape[:2]
#
#    def search_best(cx, cy, radius, step):
#        best_score = -1.0
#        best_dx, best_dy = cx, cy
#        for dy in range(cy - radius, cy + radius + 1, step):
#            for dx in range(cx - radius, cx + radius + 1, step):
#                by, bx, ty, tx = alignment_overlap_slices((h, w), dx, dy)
#                if by.stop <= by.start or bx.stop <= bx.start:
#                    continue
#                score = ncc_score(base_f[by, bx], target_f[ty, tx])
#                if score > best_score:
#                    best_score = score
#                    best_dx = dx
#                    best_dy = dy
#        return best_dx, best_dy, best_score
#
#    # Stage 1: Coarse search (step=4)
#    coarse_step = 4
#    coarse_dx, coarse_dy, _ = search_best(0, 0, search_radius, coarse_step)
#
#    # Stage 2: Fine search (step=1) around coarse result
#    fine_radius = coarse_step
#    best_dx, best_dy, best_score = search_best(coarse_dx, coarse_dy, fine_radius, 1)
#
#    # Stage 3: Parabolic sub-pixel refinement on the NCC surface
#    # Fit parabola along each axis at the integer peak.
#    def _ncc_at(ddx, ddy):
#        by, bx, ty, tx = alignment_overlap_slices((h, w), ddx, ddy)
#        if by.stop <= by.start or bx.stop <= bx.start:
#            return -1.0
#        return ncc_score(base_f[by, bx], target_f[ty, tx])
#
#    def _parabolic_offset(f_neg, f_0, f_pos):
#        denom = 2.0 * (f_pos - 2.0 * f_0 + f_neg)
#        if abs(denom) < 1e-8:
#            return 0.0
#        return -(f_pos - f_neg) / denom
#
#    dx_sub = best_dx + _parabolic_offset(
#        _ncc_at(best_dx - 1, best_dy),
#        best_score,
#        _ncc_at(best_dx + 1, best_dy),
#    )
#    dy_sub = best_dy + _parabolic_offset(
#        _ncc_at(best_dx, best_dy - 1),
#        best_score,
#        _ncc_at(best_dx, best_dy + 1),
#    )
#
#    aligned_target = apply_alignment(target_f.astype(np.float32), dx_sub, dy_sub)
#    residual = float(np.mean(np.abs(base_f - aligned_target)))
#    score_residual = max(0.0, 1.0 - residual * 2.0)
#    score_ncc = (best_score + 1.0) / 2.0
#    final_score = (0.6 * score_ncc + 0.4 * score_residual) * 100.0
#
#    status = 'ok'
#    if final_score < 75:
#        status = 'warn'
#    if final_score < 55:
#        status = 'fail'
#
#    return AlignResult(
#        dx=int(best_dx),
#        dy=int(best_dy),
#        score_phase=0.0,
#        score_ncc=score_ncc,
#        score_residual=score_residual,
#        final_score=final_score,
#        status=status,
#        method='ncc',
#        dx_subpixel=float(dx_sub),
#        dy_subpixel=float(dy_sub),
#    )
#
#
## ---------------------------------------------------------------------------
## ECC backend
## ---------------------------------------------------------------------------
#
#def _calculate_alignment_ecc(
#    base: np.ndarray,
#    target: np.ndarray,
#    search_radius: int = 40
#) -> AlignResult:
#    """ECC (Enhanced Correlation Coefficient) alignment.
#
#    Strategy:
#    1. Run Phase Correlation for a fast initial shift estimate.
#    2. Refine with cv2.findTransformECC on percentile-normalised grayscale.
#       ECC's criterion is inherently invariant to affine intensity changes
#       (brightness + contrast), so Sobel edge-map preprocessing is not needed
#       and would actually hurt convergence (sparse maps → near-zero gradients).
#    3. Accept the ECC result only when it stays within search_radius; otherwise
#       fall back to the Phase estimate.
#    4. Score with NCC + residual (same weights as NCC method).
#    """
#    if base is None or target is None:
#        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
#
#    # Step 1: Phase initial estimate
#    phase_result = calculate_alignment_robust(base, target, search_radius)
#
#    # Step 2: Normalise to float32 [0, 1].  ECC already handles contrast /
#    # brightness differences, so plain percentile normalisation is sufficient.
#    # Cast explicitly: normalize_image upcasts to float64 due to numpy
#    # percentile, but findTransformECC only accepts CV_8U or CV_32F.
#    base_f = normalize_image(base.astype(np.float32)).astype(np.float32)
#    target_f = normalize_image(target.astype(np.float32)).astype(np.float32)
#
#    # findTransformECC warps the input (target) with WARP_INVERSE_MAP, i.e.
#    # warped(x) = target(x + t); a target displaced by (+dx, +dy) therefore
#    # converges to t = (+dx, +dy). Seed with the phase estimate directly.
#    # (Sign fixed during vendoring — see file header.)
#    warp_matrix = np.float32([
#        [1.0, 0.0, phase_result.dx_subpixel],
#        [0.0, 1.0, phase_result.dy_subpixel],
#    ])
#
#    criteria = (
#        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
#        100,   # max iterations
#        1e-4,  # convergence epsilon
#    )
#
#    dx_ecc = phase_result.dx_subpixel
#    dy_ecc = phase_result.dy_subpixel
#
#    try:
#        # Use positional arguments for broader OpenCV version compatibility.
#        _cc, warp_out = cv2.findTransformECC(
#            base_f, target_f, warp_matrix, cv2.MOTION_TRANSLATION, criteria,
#        )
#        dx_candidate = float(warp_out[0, 2])
#        dy_candidate = float(warp_out[1, 2])
#        # Accept only when ECC stayed within the expected search range.
#        if abs(dx_candidate) <= search_radius and abs(dy_candidate) <= search_radius:
#            dx_ecc = dx_candidate
#            dy_ecc = dy_candidate
#    except cv2.error:
#        pass  # keep Phase fallback
#
#    dx_ecc = float(np.clip(dx_ecc, -search_radius, search_radius))
#    dy_ecc = float(np.clip(dy_ecc, -search_radius, search_radius))
#
#    # Score using NCC + residual on aligned overlap
#    score_ncc, score_residual, final_score = _calculate_alignment_scores(
#        base, target, int(round(dx_ecc)), int(round(dy_ecc)),
#        phase_score=0.0, method='ncc',
#    )
#
#    status = 'ok'
#    if final_score < 75:
#        status = 'warn'
#    if final_score < 55:
#        status = 'fail'
#
#    return AlignResult(
#        dx=int(round(dx_ecc)),
#        dy=int(round(dy_ecc)),
#        score_phase=phase_result.score_phase,
#        score_ncc=score_ncc,
#        score_residual=score_residual,
#        final_score=final_score,
#        status=status,
#        method='ecc',
#        dx_subpixel=dx_ecc,
#        dy_subpixel=dy_ecc,
#    )
#
#
## ---------------------------------------------------------------------------
## Template-matching backend
## ---------------------------------------------------------------------------
#
#def _calculate_alignment_template(
#    base: np.ndarray,
#    target: np.ndarray,
#    search_radius: int = 40,
#) -> AlignResult:
#    """Template-matching alignment using a centre-crop template.
#
#    Strategy:
#    1. Crop the centre (image − 2×search_radius) region of the normalised
#       base as the template; this avoids border scan-artifacts common in SEM.
#    2. Run cv2.matchTemplate(TM_CCOEFF_NORMED) against the full normalised
#       target.  OpenCV uses FFT internally → O(N log N), comparable to Phase.
#    3. Sub-pixel precision via parabolic fit on the correlation peak,
#       identical to the NCC method.
#    4. Fall back to Phase when the image is too small for the search radius.
#    """
#    if base is None or target is None:
#        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
#
#    h, w = base.shape[:2]
#    sr = search_radius
#
#    # Guard: template must be at least 8 px in each dimension
#    if h <= 2 * sr + 8 or w <= 2 * sr + 8:
#        return calculate_alignment_robust(base, target, sr)
#
#    # Normalise to float32 [0, 1]; cast explicitly to float32 because
#    # normalize_image upcasts to float64 (numpy percentile returns float64)
#    # and matchTemplate only accepts CV_8U or CV_32F.
#    base_f = normalize_image(base.astype(np.float32)).astype(np.float32)
#    target_f = normalize_image(target.astype(np.float32)).astype(np.float32)
#
#    # Template = centre crop of base; result_map shape = (2*sr+1, 2*sr+1)
#    template = base_f[sr: h - sr, sr: w - sr]
#    result_map = cv2.matchTemplate(target_f, template, cv2.TM_CCOEFF_NORMED)
#
#    # Peak location → integer shift
#    _, best_score, _, max_loc = cv2.minMaxLoc(result_map)
#    peak_x, peak_y = max_loc          # (col, row) in result_map
#    best_dx = peak_x - sr             # shift in x (cols)
#    best_dy = peak_y - sr             # shift in y (rows)
#
#    # Parabolic sub-pixel refinement along each axis
#    def _val(x: int, y: int) -> float:
#        if 0 <= y < result_map.shape[0] and 0 <= x < result_map.shape[1]:
#            return float(result_map[y, x])
#        return -1.0
#
#    def _parabolic_offset(f_neg: float, f_0: float, f_pos: float) -> float:
#        denom = 2.0 * (f_pos - 2.0 * f_0 + f_neg)
#        if abs(denom) < 1e-8:
#            return 0.0
#        return -(f_pos - f_neg) / denom
#
#    dx_sub = best_dx + _parabolic_offset(
#        _val(peak_x - 1, peak_y), best_score, _val(peak_x + 1, peak_y)
#    )
#    dy_sub = best_dy + _parabolic_offset(
#        _val(peak_x, peak_y - 1), best_score, _val(peak_x, peak_y + 1)
#    )
#
#    # Final composite score (NCC on aligned overlap + residual)
#    score_ncc, score_residual, final_score = _calculate_alignment_scores(
#        base, target, int(round(dx_sub)), int(round(dy_sub)),
#        phase_score=0.0, method='ncc',
#    )
#
#    status = 'ok'
#    if final_score < 75:
#        status = 'warn'
#    if final_score < 55:
#        status = 'fail'
#
#    return AlignResult(
#        dx=int(round(dx_sub)),
#        dy=int(round(dy_sub)),
#        score_phase=float(best_score),
#        score_ncc=score_ncc,
#        score_residual=score_residual,
#        final_score=final_score,
#        status=status,
#        method='template',
#        dx_subpixel=float(dx_sub),
#        dy_subpixel=float(dy_sub),
#    )
#
#
## ---------------------------------------------------------------------------
## Dispatcher
## ---------------------------------------------------------------------------
#
#def calculate_alignment(
#    base: np.ndarray,
#    target: np.ndarray,
#    method: str = "phase",
#    search_radius: int = 40
#) -> AlignResult:
#    """Select alignment method.
#
#    ``method`` is one of "phase", "hybrid" (alias of phase), "ncc", "ecc",
#    "template"; unknown values fall back to "phase". All backends return the
#    shift in the module-level (dx, dy) convention (see module docstring).
#    """
#    method_norm = (method or "phase").lower()
#    if base is not None and target is not None and (_is_flat(base) or _is_flat(target)):
#        # Flat-image guard: no backend can extract a shift from a constant image.
#        return AlignResult(0, 0, 0.0, 0.0, 0.0, 0.0, 'fail', 'none')
#    if method_norm in ("phase", "hybrid"):
#        return calculate_alignment_robust(base, target, search_radius)
#    if method_norm == "ncc":
#        return _calculate_alignment_ncc(base, target, search_radius)
#    if method_norm == "ecc":
#        return _calculate_alignment_ecc(base, target, search_radius)
#    if method_norm == "template":
#        return _calculate_alignment_template(base, target, search_radius)
#    return calculate_alignment_robust(base, target, search_radius)
#
#
## ---------------------------------------------------------------------------
## GLAS template alignment (SEM ↔ GDS overlay anchor correction)
## ---------------------------------------------------------------------------
#
#def parabola_subpx(res: np.ndarray, bx: int, by: int, axis: int) -> float:
#    """Sub-pixel peak offset (∈ [-1, 1]) from a 3-point parabola fit around
#    the score-map peak along ``axis`` (0 = x, 1 = y)."""
#    h, w = res.shape
#    if axis == 0:
#        if bx <= 0 or bx >= w - 1:
#            return 0.0
#        a, b, c = float(res[by, bx - 1]), float(res[by, bx]), float(res[by, bx + 1])
#    else:
#        if by <= 0 or by >= h - 1:
#            return 0.0
#        a, b, c = float(res[by - 1, bx]), float(res[by, bx]), float(res[by + 1, bx])
#    denom = a - 2.0 * b + c
#    if denom == 0.0:
#        return 0.0
#    off = 0.5 * (a - c) / denom
#    return off if abs(off) <= 1.0 else 0.0
#
#
#def template_align_nm(sem_img: np.ndarray, template_full: np.ndarray,
#                      nm_per_px: float, search_radius_px: float) -> tuple:
#    """Refine the SEM↔GDS alignment by template matching (plan M4b).
#
#    ``template_full`` is the synthetic POI rendered at the *expected* (coarse)
#    position, the same size as ``sem_img``. Its centre is cropped (leaving a
#    ``search_radius_px`` border) and slid over the SEM with
#    ``TM_CCOEFF_NORMED``; the peak's displacement from the centred position is
#    the residual misalignment. Returns ``(dx_nm, dy_nm, score, used_radius_px)``
#    where ``(dx_nm, dy_nm)`` is the correction to add to the overlay anchor so
#    the GDS lands on the SEM structure.
#
#    NOTE: unlike calculate_alignment, the return value is a GDS *anchor
#    correction* in nanometres, not an image-space (dx, dy): if the SEM
#    structure sits (ex, ey) pixels right/down of the template, this returns
#    ``(-ex * nm_per_px, +ey * nm_per_px, score, r)`` (image x is right, GDS x
#    is right, so anchor.x decreases to shift the overlay right; image y is
#    down, GDS y is up, so anchor.y increases to shift the overlay down).
#    """
#    H, W = sem_img.shape[:2]
#    if template_full.shape[:2] != (H, W):
#        raise ValueError("template must match the SEM image size")
#    r = int(round(search_radius_px))
#    r = max(1, min(r, (min(H, W) - 1) // 2))
#    tmpl = np.ascontiguousarray(template_full[r:H - r, r:W - r])
#    sem = np.ascontiguousarray(sem_img)
#    if tmpl.size == 0 or float(tmpl.std()) < 1e-6 or float(sem.std()) < 1e-6:
#        return 0.0, 0.0, 0.0, r          # flat template/image → no signal
#    res = cv2.matchTemplate(sem.astype(np.uint8), tmpl.astype(np.uint8),
#                            cv2.TM_CCOEFF_NORMED)
#    _, maxv, _, maxloc = cv2.minMaxLoc(res)
#    bx, by = int(maxloc[0]), int(maxloc[1])
#    sx = parabola_subpx(res, bx, by, 0)
#    sy = parabola_subpx(res, bx, by, 1)
#    ex = (bx + sx) - r            # SEM structure offset from GDS, +x = right
#    ey = (by + sy) - r            # +y = down (image row)
#    # Anchor correction: move the overlay onto the SEM structure. Image x is
#    # right, GDS x is right (so anchor.x decreases to shift right); image y is
#    # down, GDS y is up (so anchor.y increases to shift down).
#    return (-ex * nm_per_px, ey * nm_per_px, float(maxv), r)
#
#F a77fdc04e961b1cc81f29eb7f200d2d164791e27 144 adept/core/algo/blob.py
## ---------------------------------------------------------------------------
## Vendored into ADEPT on 2026-07-27.
## Source project: Perspective-Combination (Fusi3)
## Source file:    perscomb/core/perspective_combine.py
##                 (DefectROI, segment_defects)
## Adaptations:
##   - segment_defects now also accepts a float SNR map in [0, 1] (e.g.
##     snr.SnrMapResult.map_float): float maps with max <= 1.5 are scaled by
##     255 before thresholding, reproducing the legacy uint8 path exactly.
##     uint8 maps and 0-255-scaled float maps behave as before.
##   - DefectROI gains a `bbox` property returning (x, y, w, h).
##   - Algorithm behavior otherwise unchanged.
## ---------------------------------------------------------------------------
#"""Defect segmentation from a local SNR map (connected-component labeling)."""
#from __future__ import annotations
#
#from dataclasses import dataclass
#from typing import List, Optional, Tuple
#
#import cv2
#import numpy as np
#
#
#@dataclass
#class DefectROI:
#    """Bounding box and metrics for a single detected defect region."""
#    x: int
#    y: int
#    w: int
#    h: int
#    cx: float                # centroid x
#    cy: float                # centroid y
#    area: int                # pixel count
#    mean_signal: float       # mean diff_image value inside bbox
#    snr_value: float         # max SNR inside bbox (0-255 map scale)
#    aspect_ratio: float      # w / h
#    dist_to_center: float    # Euclidean distance from image center (pixels)
#
#    @property
#    def bbox(self) -> Tuple[int, int, int, int]:
#        """Bounding box as a pixel-space (x, y, w, h) tuple."""
#        return (self.x, self.y, self.w, self.h)
#
#
#def _snr_map_to_uint8(snr_map: np.ndarray) -> np.ndarray:
#    """Coerce an SNR map to the 0-255 uint8 scale used for thresholding.
#
#    Accepts the legacy uint8 map, a float map already on the 0-255 scale, or
#    a normalized float map in [0, 1] (SnrMapResult.map_float), which is
#    scaled by 255 to reproduce the legacy quantization.
#    """
#    if snr_map.dtype == np.uint8:
#        return snr_map
#    map_f = snr_map.astype(np.float32)
#    if map_f.size > 0 and float(map_f.max()) <= 1.5:
#        map_f = map_f * 255.0
#    return np.clip(map_f, 0, 255).astype(np.uint8)
#
#
#def segment_defects(
#    snr_map: np.ndarray,
#    diff_image: np.ndarray,
#    min_area: int = 4,
#    snr_threshold: Optional[float] = None,
#) -> List[DefectROI]:
#    """Segment defect regions from SNR map using adaptive thresholding.
#
#    Parameters
#    ----------
#    snr_map : uint8 SNR map (0-255) or float map in [0, 1]
#              (e.g. SnrMapResult.map_float)
#    diff_image : float32 or uint8 difference image (same shape as snr_map)
#    min_area : minimum connected-component area (pixels) to keep
#    snr_threshold : manual SNR threshold (0-255 map scale); if None, Otsu is used
#
#    Returns
#    -------
#    List of DefectROI sorted by snr_value descending.
#    """
#    if snr_map is None or snr_map.size == 0:
#        return []
#
#    snr_u8 = _snr_map_to_uint8(snr_map)
#
#    # Threshold
#    if snr_threshold is not None:
#        thresh_val = int(np.clip(snr_threshold, 0, 255))
#        _, binary = cv2.threshold(snr_u8, thresh_val, 255, cv2.THRESH_BINARY)
#    else:
#        # Otsu on non-border region
#        _, binary = cv2.threshold(snr_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
#
#    # Morphological clean-up: remove isolated noise, fill small gaps
#    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
#    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
#    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
#
#    # Connected components
#    n_labels, labels, stats_cc, centroids = cv2.connectedComponentsWithStats(
#        binary, connectivity=8
#    )
#
#    H, W = snr_map.shape[:2]
#    img_cx, img_cy = W / 2.0, H / 2.0
#
#    diff_f = diff_image.astype(np.float32)
#    if diff_f.max() > 1.5:
#        diff_f = diff_f / 255.0
#
#    rois: List[DefectROI] = []
#    for label_idx in range(1, n_labels):  # skip background (label 0)
#        area = int(stats_cc[label_idx, cv2.CC_STAT_AREA])
#        if area < min_area:
#            continue
#
#        bx = int(stats_cc[label_idx, cv2.CC_STAT_LEFT])
#        by = int(stats_cc[label_idx, cv2.CC_STAT_TOP])
#        bw = int(stats_cc[label_idx, cv2.CC_STAT_WIDTH])
#        bh = int(stats_cc[label_idx, cv2.CC_STAT_HEIGHT])
#        cx_roi = float(centroids[label_idx, 0])
#        cy_roi = float(centroids[label_idx, 1])
#
#        mask_roi = (labels[by:by + bh, bx:bx + bw] == label_idx)
#        diff_crop = diff_f[by:by + bh, bx:bx + bw]
#        snr_crop = snr_u8[by:by + bh, bx:bx + bw].astype(np.float32)
#
#        mean_sig = float(diff_crop[mask_roi].mean()) if mask_roi.any() else 0.0
#        snr_val = float(snr_crop[mask_roi].max()) if mask_roi.any() else 0.0
#        aspect = bw / max(bh, 1)
#        dist = float(np.hypot(cx_roi - img_cx, cy_roi - img_cy))
#
#        rois.append(DefectROI(
#            x=bx, y=by, w=bw, h=bh,
#            cx=cx_roi, cy=cy_roi,
#            area=area,
#            mean_signal=mean_sig,
#            snr_value=snr_val,
#            aspect_ratio=aspect,
#            dist_to_center=dist,
#        ))
#
#    rois.sort(key=lambda r: r.snr_value, reverse=True)
#    return rois
#
#F ed44cb755d91d7f3adf6018672969a6cb68932f0 93 adept/core/algo/curve.py
## ADEPT algorithm module — authored 2026-07-29 (F7-8).
#"""Tone curve 求值：控制點 → 查表 → 套用到影像。
#
#單調三次 Hermite（Fritsch–Carlson）
#-----------------------------------
#控制點之間用**保單調**的三次插值，不是直線也不是自然三次樣條：
#
#* 直線：拉三個點就看得到折角，而 gamma 曲線本來就該是平滑的；
#* 自然三次樣條：會 overshoot —— 使用者把中間點往上拉，曲線可能在旁邊
#  先往下凹一段。對「調亮」這個意圖來說那是錯的，而且在影像上會直接看到
#  一圈假的暗環。
#
#Fritsch–Carlson 限制斜率，保證「控制點單調上升 → 曲線也單調上升」。
#沒有 scipy —— 這是廠內離線機，相依愈少愈好（`docs/OFFLINE-INSTALL.md`）。
#
#UI 的曲線編輯器畫的就是 :func:`curve_lut` 的輸出，所以**畫面上看到的線就是
#影像上套的線**（WYSIWYG，不是各畫各的）。
#"""
#from __future__ import annotations
#
#from typing import Sequence, Tuple
#
#import numpy as np
#
#from ..pipeline.curve import parse_curve
#
#__all__ = ["curve_lut", "eval_curve", "apply_curve_01"]
#
#Point = Tuple[float, float]
#
##: LUT 的取樣數。256 對 uint8 是一格一階；float 影像也夠細
##: （再細的差異會被下游的 diff/量測吃掉）。
#LUT_SIZE = 256
#
#
#def eval_curve(points: Sequence[Point], xs: np.ndarray) -> np.ndarray:
#    """在 ``xs``（0–1）上求曲線值，回傳同 shape 的 float64（已夾在 0–1）。"""
#    pts = [(float(x), float(y)) for x, y in points]
#    x = np.asarray([p[0] for p in pts], dtype=np.float64)
#    y = np.asarray([p[1] for p in pts], dtype=np.float64)
#    n = x.size
#    if n < 2:
#        return np.clip(np.asarray(xs, dtype=np.float64), 0.0, 1.0)
#
#    h = np.diff(x)
#    delta = np.diff(y) / h                      # 各段割線斜率
#
#    # 端點取單邊割線、內點取兩側平均，再用 Fritsch–Carlson 收斂到保單調的範圍
#    m = np.empty(n, dtype=np.float64)
#    m[0] = delta[0]
#    m[-1] = delta[-1]
#    if n > 2:
#        m[1:-1] = (delta[:-1] + delta[1:]) / 2.0
#    for i in range(n - 1):
#        if delta[i] == 0.0:                     # 平段：兩端斜率都必須是 0
#            m[i] = m[i + 1] = 0.0
#            continue
#        a, b = m[i] / delta[i], m[i + 1] / delta[i]
#        s = a * a + b * b
#        if s > 9.0:                             # 落在單調區之外 → 等比例縮回來
#            t = 3.0 / float(np.sqrt(s))
#            m[i] = t * a * delta[i]
#            m[i + 1] = t * b * delta[i]
#
#    q = np.clip(np.asarray(xs, dtype=np.float64), 0.0, 1.0)
#    idx = np.clip(np.searchsorted(x, q, side="right") - 1, 0, n - 2)
#    hi = h[idx]
#    t = (q - x[idx]) / hi
#    t2, t3 = t * t, t * t * t
#    out = ((2 * t3 - 3 * t2 + 1) * y[idx]
#           + (t3 - 2 * t2 + t) * hi * m[idx]
#           + (-2 * t3 + 3 * t2) * y[idx + 1]
#           + (t3 - t2) * hi * m[idx + 1])
#    return np.clip(out, 0.0, 1.0)
#
#
#def curve_lut(curve, size: int = LUT_SIZE) -> np.ndarray:
#    """曲線（字串或控制點）→ ``size`` 個等距取樣的查表（float64，0–1）。"""
#    pts = parse_curve(curve) if isinstance(curve, str) else list(curve)
#    n = max(2, int(size))
#    return eval_curve(pts, np.linspace(0.0, 1.0, n))
#
#
#def apply_curve_01(x01: np.ndarray, curve, size: int = LUT_SIZE) -> np.ndarray:
#    """把已經正規化到 0–1 的陣列套上曲線。
#
#    走 LUT + ``np.interp`` 而不是每個像素解一次 Hermite ——
#    一張 128² patch 只要 256 次多項式求值，其餘是一次線性內插。
#    """
#    lut = curve_lut(curve, size)
#    grid = np.linspace(0.0, 1.0, lut.size)
#    return np.interp(np.clip(x01, 0.0, 1.0), grid, lut)
#
#F 31ed355760ee79e887ddc627c0bc970c77bdfe42 221 adept/core/algo/enhance.py
## ADEPT algorithm library — authored 2026-07-29 (F7-10).
#"""局部對比、背景/條紋移除、邊緣保留去噪 —— E-beam patch 常見 artifact 的處理。
#
#為什麼這三件事值得放進來
#------------------------
#既有的 Enhance 卡都是**全域**的（percentile / gamma / curve / 亮度對比）：
#它們對整張圖套同一條轉換曲線。但 E-beam patch 上最常見的三種假訊號都是
#**空間性**的，全域轉換一個都處理不掉：
#
#1. **charging 造成的大範圍亮度梯度** —— 一角亮一角暗。全域拉伸只會把梯度
#   一起拉大；而 test 與 ref 的梯度不會一樣，於是它整片留在 diff 上。
#2. **掃描線條紋（line-scan artifact）** —— 逐行或逐列的增益漂移。
#   在 diff 上會變成一條一條的假缺陷，而且 blob 分割抓得到它。
#3. **局部暗區裡的小缺陷** —— 全域 percentile 用的是整張圖的分布，
#   暗區裡的對比再怎麼拉都還是被亮區決定。
#
#三者的共通結構是「先估一個**大尺度**的成分，再把它拿掉」，所以下面的函式
#都長成同一個形狀：估計 → 相減 → 還原亮度基準。
#
#dtype 慣例
#----------
#一律 float32 進、float32 出（`clahe` 例外：CLAHE 只吃整數，內部轉 uint8），
#由呼叫端（step 卡）決定要不要轉回原 dtype —— 跟 `algo/normalize.py` 同慣例。
#"""
#from __future__ import annotations
#
#from typing import Any
#
#import cv2
#import numpy as np
#
#__all__ = [
#    "clahe", "remove_background", "remove_stripes", "morph_residual",
#    "bilateral", "nlm", "noise_sigma",
#]
#
#
#def _as_f32(img: Any) -> np.ndarray:
#    return np.asarray(img).astype(np.float32, copy=False)
#
#
#def _odd(n: int) -> int:
#    """把核心大小修成奇數（偶數核沒有中心像素）。"""
#    n = max(1, int(n))
#    return n if n % 2 == 1 else n + 1
#
#
##: Immerkær 的拉普拉斯遮罩（雜訊估計用）。
#_NOISE_MASK = np.array([[1.0, -2.0, 1.0],
#                        [-2.0, 4.0, -2.0],
#                        [1.0, -2.0, 1.0]], dtype=np.float32)
#
#
#def noise_sigma(img: Any) -> float:
#    """估計影像的雜訊標準差（Immerkær 1996），單位是灰階值。
#
#    為什麼保留邊緣的去噪一定要先估這個
#    ----------------------------------
#    ``bilateral`` / ``nlm`` 的強度參數單位是**灰階值**：它要回答的是
#    「差多少以內算同一塊」。直接給常數的話，同一組參數換一台機台、換一個
#    曝光條件就完全不對 —— 而使用者會以為是自己參數調錯。
#
#    以雜訊為尺度就穩定了：``strength=1`` 的意思固定是「濾掉一個 σ 的擾動」，
#    不管這個 lot 的訊號有多亮、動態範圍有多寬。
#
#    這個估計法用拉普拉斯遮罩對雜訊的響應算，對影像**內容**（邊緣、圖樣）
#    幾乎免疫，而且只要一次卷積。
#    """
#    f = _as_f32(img)
#    if f.ndim != 2 or f.shape[0] < 3 or f.shape[1] < 3:
#        return float(np.std(f)) if f.size else 0.0
#    h, w = f.shape
#    conv = cv2.filter2D(f, -1, _NOISE_MASK, borderType=cv2.BORDER_REPLICATE)
#    sigma = np.sqrt(np.pi / 2.0) * float(np.sum(np.abs(conv))) \
#        / (6.0 * (w - 2) * (h - 2))
#    return float(max(sigma, 1e-3))
#
#
#def clahe(img: Any, clip_limit: float = 2.0, tiles: int = 8) -> np.ndarray:
#    """CLAHE（限制對比的自適應直方圖等化）。回傳 float32（值域 0–255）。
#
#    每個 tile 各自做直方圖等化，所以**暗區裡的小缺陷也拉得起來** ——
#    這正是全域 percentile 做不到的事。``clip_limit`` 是對比上限：
#    沒有它，平坦區域的雜訊會被放大到跟訊號一樣強（這也是為什麼不用
#    普通的 histogram equalization）。
#
#    ``tiles`` 是格子數（8 = 8×8）。格子越小越貼合局部，但也越容易把
#    **缺陷本身**當成局部背景吃掉 —— 缺陷比一個 tile 大的時候要調小格數。
#    """
#    # CLAHE 只吃 8/16-bit 整數；先把值域壓到 0–255 再轉 uint8
#    f = _as_f32(img)
#    if f.size == 0:
#        return f.copy()
#    lo, hi = float(np.nanmin(f)), float(np.nanmax(f))
#    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
#        return f.copy()
#    u8 = np.clip((f - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
#
#    n = max(1, int(tiles))
#    op = cv2.createCLAHE(clipLimit=max(0.01, float(clip_limit)),
#                         tileGridSize=(n, n))
#    return op.apply(u8).astype(np.float32)
#
#
#def remove_background(img: Any, size: int = 31,
#                      keep_level: bool = True) -> np.ndarray:
#    """大尺度背景移除：``img - blur(img)``（+ 原本的平均值）。
#
#    ``size`` 是背景估計的模糊核心。**它必須明顯大於缺陷** ——
#    核心太小的話，缺陷自己會被算進背景裡然後被減掉（訊號消失）。
#    經驗值：抓 patch 邊長的 1/4 ~ 1/2。
#
#    ``keep_level=True`` 會把原影像的平均值加回去，讓輸出仍然落在原本的
#    亮度區間 —— 不然後面每一張看灰階絕對值的卡（glv_stats、門檻）都要重調。
#    """
#    f = _as_f32(img)
#    if f.size == 0:
#        return f.copy()
#    k = _odd(size)
#    bg = cv2.GaussianBlur(f, (k, k), 0, borderType=cv2.BORDER_REPLICATE)
#    out = f - bg
#    if keep_level and f.size:
#        out = out + float(np.nanmean(f))
#    return out.astype(np.float32)
#
#
#def remove_stripes(img: Any, axis: int = 0, strength: float = 1.0) -> np.ndarray:
#    """掃描線去條紋：把每一列（或每一行）的中位數拉齊到全域中位數。
#
#    ``axis=0`` 移除**水平**條紋（逐列校正，適合逐行掃描的 SEM）；
#    ``axis=1`` 移除垂直條紋。
#
#    用**中位數**而不是平均值是關鍵：一顆夠大的缺陷會把該列的平均值整個帶偏，
#    校正時就會在缺陷所在的那一列造成一條反向的假條紋。中位數對它免疫。
#
#    ``strength`` 0–1 是校正比例（1 = 完全拉齊）。留這個旋鈕是因為真實條紋
#    通常不是純加性的；全量校正偶爾會過頭。
#    """
#    f = _as_f32(img)
#    if f.ndim != 2 or f.size == 0:
#        return f.copy()
#    a = 0 if int(axis) == 0 else 1
#    # axis=0（水平條紋）-> 每一列一個中位數
#    prof = np.nanmedian(f, axis=1 - a)
#    global_med = float(np.nanmedian(f))
#    delta = (prof - global_med) * float(np.clip(strength, 0.0, 1.0))
#    if a == 0:
#        return (f - delta[:, None]).astype(np.float32)
#    return (f - delta[None, :]).astype(np.float32)
#
#
#def morph_residual(img: Any, size: int = 15, dark: bool = False) -> np.ndarray:
#    """形態學殘差：white top-hat（亮）或 black-hat（暗）。
#
#    top-hat = ``img - open(img)``：留下**比核心小的亮物**，把大尺度背景
#    （不管形狀多不規則）整個拿掉。比高斯背景移除更適合「背景不平滑、
#    但缺陷很小」的情況 —— 圖樣邊緣不會被算成背景梯度。
#
#    ``dark=True`` 走 black-hat（``close(img) - img``），對應暗缺陷。
#    ``size`` 同樣要**大於缺陷**，否則缺陷會被開運算吃掉。
#    """
#    f = _as_f32(img)
#    if f.size == 0:
#        return f.copy()
#    k = _odd(size)
#    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
#    op = cv2.MORPH_BLACKHAT if dark else cv2.MORPH_TOPHAT
#    return cv2.morphologyEx(f, op, kernel,
#                            borderType=cv2.BORDER_REPLICATE).astype(np.float32)
#
#
#def bilateral(img: Any, size: int = 5, strength: float = 1.0) -> np.ndarray:
#    """雙邊濾波：平滑雜訊但**保留邊緣**。
#
#    median 與 gaussian 都會把小缺陷連同雜訊一起抹掉（median 對「比核心小的
#    亮點」尤其致命 —— 那正是我們要找的東西）。雙邊濾波只平滑**灰階相近**的
#    鄰居，所以缺陷與圖樣的邊界留得住。
#
#    ``strength`` 以**這張圖自己的雜訊 σ** 為單位（見 :func:`noise_sigma`）：
#    ``1`` = 只抹掉大約一個 σ 的擾動，換一個 lot 也還是同一個意思。
#    """
#    f = _as_f32(img)
#    if f.size == 0:
#        return f.copy()
#    d = _odd(size)
#    sigma_color = max(1.0, 1.5 * noise_sigma(f) * float(max(0.01, strength)))
#    return cv2.bilateralFilter(f, d, sigma_color, float(d)).astype(np.float32)
#
#
#def nlm(img: Any, size: int = 7, strength: float = 1.0) -> np.ndarray:
#    """Non-local means：拿整張圖裡「長得像」的區塊來平均。
#
#    比雙邊濾波更會保留**紋理**（重複圖樣的 patch 正好有很多相似區塊可用），
#    代價是慢一個數量級。整批跑之前先在單顆預覽上確認值得。
#
#    只吃 uint8（OpenCV 的限制），所以內部會把值域壓到 0–255 再還原。
#    """
#    f = _as_f32(img)
#    if f.size == 0:
#        return f.copy()
#    lo, hi = float(np.nanmin(f)), float(np.nanmax(f))
#    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
#        return f.copy()
#    # ``h`` 的單位是**灰階值**，所以轉 uint8 時能不拉伸就不拉伸：
#    # 一張 100–165 的圖如果先被拉滿 0–255，雜訊也跟著放大 4 倍，
#    # 同一個 h 就從「剛好」變成「幾乎沒有作用」——
#    # 使用者會看到「strength 拉到底還是很雜」，而原因跟他的參數無關。
#    if lo >= -0.5 and hi <= 255.5:
#        u8 = np.clip(f, 0.0, 255.0).astype(np.uint8)
#        scale, offset = 1.0, 0.0
#        sigma = noise_sigma(f)
#    else:
#        u8 = np.clip((f - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
#        scale, offset = (hi - lo) / 255.0, lo
#        sigma = noise_sigma(u8.astype(np.float32))   # σ 要跟 h 同一個尺度
#    # h ≈ 一個雜訊 σ 就已經把雜訊壓掉九成而缺陷完好；再往上（2σ 起）
#    # 小缺陷會開始跟著消失，所以預設 strength=1 就停在這裡。
#    h = max(1.0, sigma * float(max(0.01, strength)))
#    out = cv2.fastNlMeansDenoising(u8, None, h, 7, _odd(size) + 2 * 3)
#    return (out.astype(np.float32) * scale + offset).astype(np.float32)
#
#F 9e85e8aedef61131545e67fef5e323dbb56a5d57 212 adept/core/algo/glv.py
## Vendored into ADEPT on 2026-07-27.
## Source project: PEAR
##   - pear/core/attributes.py  (GLV metric bank: glv_value, glv_stats,
##     metric_label, metric_formula, quantile_of, default_metrics)
##   - pear/core/analysis.py    (roi_patch, roi_metric, group_snr,
##     pixel_hist, summarize + minimal ROI dataclass they depend on)
## Adaptations:
##   - Merged the metric bank and the pure ROI/patch helpers into one module.
##   - SKIPPED PEAR's `snr(target, reference)` function: the canonical SNR
##     primitive lives in `adept.core.algo.snr` (see comment below).
##   - Vendored the minimal `ROI` dataclass / `Rect` alias (group_snr and
##     roi_metric operate on them); Qt-free in the source already.
##   - Dropped PEAR's Qt-adjacent orchestration (Group/Chart/AnalysisResult,
##     palettes, JSON (de)serialization, compute_analysis) — out of scope.
##   - No algorithmic changes.
#"""GLV(灰度值)统计与 ROI 度量 — vendored from PEAR.
#
#Deliberately small: grey-level-value (GLV) statistics of a region plus
#per-group SNR. Everything is plain NumPy and every reduction is guarded
#so degenerate / tiny patches never raise.
#
#GLV statistic ids are stable strings; custom quantiles use the id form
#``glv_q<NN>`` (e.g. ``glv_q90``).
#"""
#
#from __future__ import annotations
#
#from dataclasses import dataclass
#from typing import Dict, List, Optional, Tuple
#
#import numpy as np
#
## NOTE: the canonical e-beam SNR primitive `(mean_T - mean_R) / std_R` for
## two raw pixel arrays lives in `adept.core.algo.snr` (maintained
## separately). It is deliberately NOT imported at module import time to
## avoid import-ordering issues while the algo package is being assembled;
## import it lazily where needed. `group_snr` below keeps its own inline
## (mu_T - mu_R) / sigma_R math, which matches that canonical *signed*
## convention.
#
## Fixed GLV statistics: id -> display label. Q25/Q75 are quantiles too, but
## are shown by default, so they live in the fixed set.
#GLV_STATS: Dict[str, str] = {
#    "glv_mean": "GLV mean",
#    "glv_median": "GLV median",
#    "glv_q25": "GLV Q25",
#    "glv_q75": "GLV Q75",
#    "glv_std": "GLV std",
#    "glv_min": "GLV min",
#    "glv_max": "GLV max",
#}
#
## Short formulas, shown as tooltips.
#GLV_FORMULAS: Dict[str, str] = {
#    "glv_mean": "mean(gray)",
#    "glv_median": "median(gray)",
#    "glv_q25": "25th percentile",
#    "glv_q75": "75th percentile",
#    "glv_std": "std(gray)",
#    "glv_min": "min(gray)",
#    "glv_max": "max(gray)",
#}
#
#SNR_ID = "snr"
#SNR_LABEL = "SNR"
#SNR_FORMULA = "(mean_T − mean_R) / std_R"
#
#_EPS = 1e-9
#
#Rect = Tuple[int, int, int, int]      # (x, y, w, h) in image pixels
#
#
#@dataclass
#class ROI:
#    """A measurement rectangle belonging to one group."""
#
#    rid: int
#    gid: str
#    rect: Rect
#    label: str = ""
#
#
#def quantile_of(mid: str) -> Optional[int]:
#    """Percentile for a quantile metric id (``glv_q90`` -> 90), else None."""
#    if mid.startswith("glv_q") and mid[5:].isdigit():
#        return int(mid[5:])
#    return None
#
#
#def metric_label(mid: str) -> str:
#    """Human label for any metric id (fixed, custom quantile, or SNR)."""
#    if mid in GLV_STATS:
#        return GLV_STATS[mid]
#    if mid == SNR_ID:
#        return SNR_LABEL
#    q = quantile_of(mid)
#    if q is not None:
#        return f"GLV Q{q}"
#    return mid
#
#
#def metric_formula(mid: str) -> str:
#    if mid in GLV_FORMULAS:
#        return GLV_FORMULAS[mid]
#    if mid == SNR_ID:
#        return SNR_FORMULA
#    q = quantile_of(mid)
#    if q is not None:
#        return f"{q}th percentile"
#    return "—"
#
#
#def glv_value(patch: np.ndarray, mid: str) -> float:
#    """One GLV statistic of a patch. Custom quantiles (``glv_q<NN>``) work too."""
#    f = np.asarray(patch, dtype=np.float64).ravel()
#    if f.size == 0:
#        return 0.0
#    if mid == "glv_mean":
#        return float(f.mean())
#    if mid == "glv_std":
#        return float(f.std())
#    if mid == "glv_min":
#        return float(f.min())
#    if mid == "glv_max":
#        return float(f.max())
#    if mid == "glv_median":
#        return float(np.median(f))
#    q = quantile_of(mid)
#    if q is not None:
#        return float(np.percentile(f, q))
#    return 0.0
#
#
#def glv_stats(patch: np.ndarray) -> Dict[str, float]:
#    """The full fixed GLV statistic set for a patch."""
#    return {mid: glv_value(patch, mid) for mid in GLV_STATS}
#
#
#def default_metrics() -> List[str]:
#    """Metrics selected on first run."""
#    return ["glv_mean", "glv_median"]
#
#
## --------------------------------------------------------------------------- #
## ROI patch + metrics
## --------------------------------------------------------------------------- #
#def roi_patch(image: np.ndarray, rect: Rect) -> Optional[np.ndarray]:
#    """Clipped ROI patch, or None if it lies fully outside the image."""
#    x, y, w, h = rect
#    ih, iw = image.shape[:2]
#    x0, y0 = max(0, x), max(0, y)
#    x1, y1 = min(iw, x + w), min(ih, y + h)
#    if x1 <= x0 or y1 <= y0:
#        return None
#    return image[y0:y1, x0:x1]
#
#
#def roi_metric(image: np.ndarray, roi: ROI, mid: str) -> float:
#    """A per-ROI GLV statistic (SNR is a per-group metric, not per ROI)."""
#    p = roi_patch(image, roi.rect)
#    return glv_value(p, mid) if p is not None else 0.0
#
#
#def group_snr(image: np.ndarray, rois: List[ROI],
#              target_rid: Optional[int]) -> Optional[float]:
#    """Within-group SNR = (mean_target - mean_reference) / std_reference.
#
#    ``target_rid`` selects the target ROI; every other ROI in the group is
#    the reference (their pixels are pooled). Returns None when there is no
#    target, no reference, or the reference has no spread.
#
#    The inline (mu_T - mu_R) / sigma_R math matches the canonical *signed*
#    e-beam SNR convention (see `adept.core.algo.snr`).
#    """
#    tgt = next((r for r in rois if r.rid == target_rid), None)
#    refs = [r for r in rois if r.rid != target_rid]
#    if tgt is None or not refs:
#        return None
#    tp = roi_patch(image, tgt.rect)
#    if tp is None or tp.size == 0:
#        return None
#    ref_pix = [roi_patch(image, r.rect).astype(np.float64).ravel()
#               for r in refs if roi_patch(image, r.rect) is not None]
#    ref_pix = [a for a in ref_pix if a.size]
#    if not ref_pix:
#        return None
#    ref = np.concatenate(ref_pix)
#    sd = float(ref.std())
#    if sd < 1e-9:
#        return None
#    return (float(tp.astype(np.float64).mean()) - float(ref.mean())) / sd
#
#
#def pixel_hist(patch, bins: int = 32):
#    """Grey-level histogram of a patch over the full 0–255 range."""
#    p = np.asarray(patch).ravel()
#    if p.size == 0:
#        return np.zeros(bins, dtype=int), np.linspace(0, 255, bins + 1)
#    return np.histogram(p, bins=bins, range=(0, 255))
#
#
#def summarize(values: np.ndarray) -> Dict[str, float]:
#    v = np.asarray(values, dtype=np.float64)
#    v = v[np.isfinite(v)]
#    if v.size == 0:
#        return {"n": 0, "mean": 0.0, "std": 0.0, "median": 0.0,
#                "q25": 0.0, "q75": 0.0, "min": 0.0, "max": 0.0}
#    return {"n": int(v.size), "mean": float(v.mean()), "std": float(v.std()),
#            "median": float(np.median(v)), "q25": float(np.percentile(v, 25)),
#            "q75": float(np.percentile(v, 75)), "min": float(v.min()),
#            "max": float(v.max())}
#
#F a77ccf39e51b71d68671878245eed04422b4f24e 156 adept/core/algo/golden.py
## Vendored into ADEPT on 2026-07-27.
## Source project: cell-period-estimator —
##   cell_period_estimator/core/stacking.py (vendored wholesale)
## Adaptations:
##   - Module vendored unchanged (pure NumPy/OpenCV, no Qt in the source).
##   - No algorithmic changes.
#"""Golden-Cell stacking and sharpness scoring.
#
#Pure NumPy / OpenCV.  Given a period ``(px, py)`` these helpers tile the
#image into cells and average / median them into a single "Golden Cell".
#When the period is correct the cells align and the stack is sharp; when
#it is wrong the cells drift and the stack ghosts (blurs), which is what
#the sharpness metrics quantify.
#"""
#
#from __future__ import annotations
#
#from typing import List, Optional, Tuple
#
#import cv2
#import numpy as np
#
#
#def _to_gray(image: np.ndarray) -> np.ndarray:
#    arr = np.asarray(image)
#    if arr.ndim == 3:
#        if arr.shape[2] == 4:
#            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
#        else:
#            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
#    return arr
#
#
#def tile_coords(shape: Tuple[int, ...], px: int, py: int,
#                origin: Tuple[int, int] = (0, 0)) -> List[Tuple[int, int]]:
#    """Top-left ``(x, y)`` of every *complete* cell.
#
#    Cells that would run past the image border are skipped.  This is the
#    single source of truth for cell placement used by both stacking and
#    period refinement.
#    """
#    h, w = shape[:2]
#    ox, oy = origin
#    px, py = int(px), int(py)
#    if px < 1 or py < 1:
#        return []
#    xs = range(ox, w - px + 1, px)
#    ys = range(oy, h - py + 1, py)
#    return [(x, y) for y in ys for x in xs]
#
#
#def stack_cells(image: np.ndarray, px: int, py: int, method: str = "mean",
#                origin: Tuple[int, int] = (0, 0),
#                sample_n: Optional[int] = None, seed: int = 0) -> np.ndarray:
#    """Stack all (or ``sample_n`` random) cells into one ``(py, px)`` image.
#
#    ``method="mean"`` (default) is sensitive to phase error and makes
#    ghosting obvious; ``method="median"`` is robust to sparse defects.
#    """
#    gray = _to_gray(image)
#    px, py = int(px), int(py)
#    coords = tile_coords(gray.shape, px, py, origin)
#    if not coords:
#        return np.zeros((max(py, 1), max(px, 1)), dtype=np.uint8)
#
#    if sample_n is not None and 0 < sample_n < len(coords):
#        rng = np.random.default_rng(seed)
#        idx = rng.choice(len(coords), size=sample_n, replace=False)
#        coords = [coords[i] for i in idx]
#
#    cells = np.stack([
#        gray[y:y + py, x:x + px].astype(np.float64) for (x, y) in coords
#    ])
#    if method == "median":
#        stacked = np.median(cells, axis=0)
#    else:
#        stacked = cells.mean(axis=0)
#    return np.clip(stacked, 0, 255).astype(np.uint8)
#
#
#def ghosting_score(stacked: np.ndarray) -> Tuple[float, float, float]:
#    """Quantify the sharpness of a stacked cell.
#
#    Returns ``(score_0_100, laplacian_var, edge_contrast)``.  ``score``
#    is a saturating 0..100 mapping for display; ``laplacian_var`` is the
#    raw (unsaturated) value callers should rank by.
#    """
#    g = stacked.astype(np.float64)
#    if g.size == 0:
#        return 0.0, 0.0, 0.0
#    lap_var = float(cv2.Laplacian(g, cv2.CV_64F).var())
#    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3)
#    gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
#    edge_contrast = float(np.hypot(gx, gy).mean())
#    # Saturating map: high lap_var -> sharp -> approaches 100.
#    score = float(np.clip(100.0 * (1.0 - np.exp(-lap_var / 200.0)), 0.0, 100.0))
#    return score, lap_var, edge_contrast
#
#
#def refine_period(image: np.ndarray, px: int, py: int, search: int = 6,
#                  method: str = "mean") -> Tuple[int, int, float]:
#    """Neighbourhood scan around ``(px, py)`` for the sharpest stack.
#
#    Candidates are ranked by the **raw** Laplacian variance (not the
#    saturating 0..100 score, which would clip and lose ordering near the
#    top).  Returns ``(best_px, best_py, best_lap_var)``.
#    """
#    gray = _to_gray(image)
#    px, py = int(px), int(py)
#    search = int(search)
#
#    best_px, best_py, best_lv = px, py, -1.0
#    for dy in range(-search, search + 1):
#        for dx in range(-search, search + 1):
#            cpx, cpy = px + dx, py + dy
#            if cpx < 2 or cpy < 2:
#                continue
#            coords = tile_coords(gray.shape, cpx, cpy)
#            if len(coords) < 4:
#                continue
#            stacked = stack_cells(gray, cpx, cpy, method=method)
#            lv = float(cv2.Laplacian(stacked.astype(np.float64),
#                                     cv2.CV_64F).var())
#            if lv > best_lv:
#                best_lv, best_px, best_py = lv, cpx, cpy
#    return best_px, best_py, best_lv
#
#
#def candidate_periods(px: int, py: int, lo: int, hi: int
#                      ) -> List[Tuple[int, int]]:
#    """Period candidates around the primary ``(px, py)``.
#
#    Includes the primary plus per-axis and combined half/double
#    harmonics, filtering out-of-range and duplicate entries.
#    """
#    out: List[Tuple[int, int]] = []
#    seen = set()
#
#    def add(a, b):
#        a, b = int(a), int(b)
#        if not (lo <= a <= hi and lo <= b <= hi):
#            return
#        if (a, b) in seen:
#            return
#        seen.add((a, b))
#        out.append((a, b))
#
#    add(px, py)             # primary
#    add(px // 2, py)        # px/2
#    add(2 * px, py)         # 2px
#    add(px, py // 2)        # py/2
#    add(px, 2 * py)         # 2py
#    add(px // 2, py // 2)   # half
#    add(2 * px, 2 * py)     # double
#    return out
#
#F 48cc527868f1d0336d9ed15803aaf54910347842 127 adept/core/algo/histmatch.py
## ---------------------------------------------------------------------------
## Vendored into ADEPT on 2026-07-27.
## Source project: Perspective-Combination (Fusi3)
## Source file:    histogram_match_tool.py (pure-core block, lines ~45-166:
##                 match_histogram_exact, match_histogram_linear,
##                 match_histogram_percentile, _MATCH_FN, compute_histogram,
##                 image_stats)
## Adaptations:
##   - Qt (PySide6) and matplotlib imports removed; only the pure-numpy core
##     is vendored. UI method-label constants dropped.
##   - Dispatch table renamed _MATCH_FN -> MATCH_FN and re-keyed by short
##     method ids: "exact", "linear", "percentile" (was UI display strings).
##   - Algorithm behavior unchanged.
## ---------------------------------------------------------------------------
#"""Histogram matching of grayscale SEM images (8-bit and 16-bit).
#
#Match a source image's brightness/contrast to a reference image using one of
#three methods, selectable through the ``MATCH_FN`` dispatch table:
#
#- ``"exact"``      : CDF-inversion exact histogram matching.
#- ``"linear"``     : mean/std shift-and-scale (preserves histogram shape).
#- ``"percentile"`` : P2/P98 linear stretch (robust to outliers).
#"""
#from __future__ import annotations
#
#from typing import Tuple
#
#import numpy as np
#
#
#def match_histogram_exact(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
#    """CDF-based exact histogram matching.
#
#    Maps the source histogram to match the reference histogram exactly
#    via cumulative distribution function inversion.
#    Supports 8-bit and 16-bit grayscale.
#    """
#    src_dtype = source.dtype
#    max_val = 65536 if src_dtype == np.uint16 else 256
#
#    src_hist, _ = np.histogram(source.flatten(), bins=max_val, range=(0, max_val))
#    ref_hist, _ = np.histogram(reference.flatten(), bins=max_val, range=(0, max_val))
#
#    src_cdf = src_hist.cumsum().astype(np.float64)
#    ref_cdf = ref_hist.cumsum().astype(np.float64)
#    src_cdf /= src_cdf[-1]
#    ref_cdf /= ref_cdf[-1]
#
#    mapping = np.interp(src_cdf, ref_cdf, np.arange(max_val)).astype(src_dtype)
#    return mapping[source]
#
#
#def match_histogram_linear(source: np.ndarray, reference: np.ndarray) -> np.ndarray:
#    """Linear normalisation — shift & scale so mean/std match reference.
#
#    Preserves the original histogram *shape* while aligning brightness
#    and contrast.  Most natural-looking result for SEM images.
#    """
#    src_dtype = source.dtype
#    max_val = 65535 if src_dtype == np.uint16 else 255
#
#    src_f = source.astype(np.float64)
#    ref_f = reference.astype(np.float64)
#
#    s_mean, s_std = src_f.mean(), src_f.std()
#    r_mean, r_std = ref_f.mean(), ref_f.std()
#
#    if s_std < 1e-6:
#        return source.copy()
#
#    result = (src_f - s_mean) * (r_std / s_std) + r_mean
#    return np.clip(result, 0, max_val).astype(src_dtype)
#
#
#def match_histogram_percentile(source: np.ndarray, reference: np.ndarray,
#                               low: float = 2.0, high: float = 98.0) -> np.ndarray:
#    """Percentile-based linear stretch.
#
#    Maps the [P_low, P_high] range of the source to match that of the
#    reference.  More robust to outliers than mean/std.
#    """
#    src_dtype = source.dtype
#    max_val = 65535 if src_dtype == np.uint16 else 255
#
#    src_f = source.astype(np.float64)
#    ref_f = reference.astype(np.float64)
#
#    s_lo, s_hi = np.percentile(src_f, [low, high])
#    r_lo, r_hi = np.percentile(ref_f, [low, high])
#
#    if (s_hi - s_lo) < 1e-6:
#        return source.copy()
#
#    scale = (r_hi - r_lo) / (s_hi - s_lo)
#    result = (src_f - s_lo) * scale + r_lo
#    return np.clip(result, 0, max_val).astype(src_dtype)
#
#
## Dispatch table: method id -> matching function
#MATCH_FN = {
#    "exact": match_histogram_exact,
#    "linear": match_histogram_linear,
#    "percentile": match_histogram_percentile,
#}
#
#
#def compute_histogram(image: np.ndarray, bins: int = 256) -> Tuple[np.ndarray, np.ndarray]:
#    """Return (counts, bin_edges) for a grayscale image."""
#    max_val = 65536 if image.dtype == np.uint16 else 256
#    counts, edges = np.histogram(image.flatten(), bins=bins, range=(0, max_val))
#    return counts, edges
#
#
#def image_stats(image: np.ndarray) -> dict:
#    """Compute summary statistics for a grayscale image."""
#    flat = image.astype(np.float64).ravel()
#    p2, p50, p98 = np.percentile(flat, [2, 50, 98])
#    return {
#        "mean": flat.mean(),
#        "std": flat.std(),
#        "min": flat.min(),
#        "max": flat.max(),
#        "P2": p2,
#        "median": p50,
#        "P98": p98,
#    }
#
#F 9e8715a433ecb84d49151964ed5aea05f8c18dc4 109 adept/core/algo/normalize.py
## ---------------------------------------------------------------------------
## Vendored into ADEPT on 2026-07-27.
## Source project: Perspective-Combination (Fusi3)
## Source file:    perscomb/core/perspective_combine.py
##                 (functions _normalize_image, _percentile_range,
##                  _normalize_image_with_range, _percentile_range_glv_masked,
##                  constant _GLV_MASK_MIN_PIXELS)
## Adaptations:
##   - Leading underscores dropped from function names (public API).
##   - _GLV_MASK_MIN_PIXELS exported as GLV_MASK_MIN_PIXELS.
##   - No Qt / UI dependencies (source module had none in these functions).
##   - Algorithm behavior unchanged.
## ---------------------------------------------------------------------------
#"""Robust percentile-based image normalization primitives.
#
#All functions operate on grayscale ndarrays and map intensities into the
#[0, 1] float range using percentile anchoring (default P2/P98), optionally
#restricted to a GLV (gray-level value) band so that the normalization scale
#is anchored to a specific pattern's brightness distribution.
#"""
#from __future__ import annotations
#
#from typing import Tuple
#
#import numpy as np
#
## Minimum masked pixels required; fall back to full-image if below.
#GLV_MASK_MIN_PIXELS = 50
#
#
#def normalize_image(img: np.ndarray) -> np.ndarray:
#    """Normalize image to 0-1 float range using robust percentile scaling."""
#    if img is None or img.size == 0:
#        return img
#
#    img_f = img.astype(np.float32)
#    p2, p98 = np.percentile(img_f, [2, 98])
#    rng = p98 - p2
#    if rng < 1e-6:
#        rng = 1.0
#
#    normalized = (img_f - p2) / rng
#    return np.clip(normalized, 0, 1)
#
#
#def percentile_range(img: np.ndarray, low: float = 2.0, high: float = 98.0) -> Tuple[float, float]:
#    """Return percentile range for normalization."""
#    if img is None or img.size == 0:
#        return 0.0, 1.0
#    img_f = img.astype(np.float32)
#    p_low, p_high = np.percentile(img_f, [low, high])
#    if (p_high - p_low) < 1e-6:
#        p_high = p_low + 1.0
#    return float(p_low), float(p_high)
#
#
#def normalize_image_with_range(img: np.ndarray, p2: float, p98: float) -> np.ndarray:
#    """Normalize image to 0-1 using provided percentile range."""
#    if img is None or img.size == 0:
#        return img
#    rng = p98 - p2
#    if rng < 1e-6:
#        rng = 1.0
#    normalized = (img.astype(np.float32) - p2) / rng
#    return np.clip(normalized, 0, 1)
#
#
#def percentile_range_glv_masked(
#    img: np.ndarray,
#    glv_low: int,
#    glv_high: int,
#    low: float = 2.0,
#    high: float = 98.0,
#) -> Tuple[float, float]:
#    """Return P2/P98 computed only from pixels whose value falls in [glv_low, glv_high].
#
#    Statistics are derived exclusively from pixels inside the specified GLV range
#    (e.g. MG: 110-145, EPI: 200-255) so that the normalization scale is anchored
#    to the brightness distribution of that specific pattern, not the full image.
#
#    If fewer than GLV_MASK_MIN_PIXELS pixels satisfy the mask, the function
#    falls back to full-image percentile_range to avoid degenerate results.
#
#    Args:
#        img:      Input image (float32, values 0-255, already inverted if needed).
#        glv_low:  Lower bound of GLV mask range (inclusive, 0-255).
#        glv_high: Upper bound of GLV mask range (inclusive, 0-255).
#        low:      Low percentile (default 2.0).
#        high:     High percentile (default 98.0).
#
#    Returns:
#        (p_low, p_high) computed from the masked pixel subset.
#    """
#    if img is None or img.size == 0:
#        return 0.0, 1.0
#
#    img_f = img.astype(np.float32)
#    mask = (img_f >= float(glv_low)) & (img_f <= float(glv_high))
#    masked_pixels = img_f[mask]
#
#    if masked_pixels.size < GLV_MASK_MIN_PIXELS:
#        # Not enough pixels in the specified range — fall back to full-image percentile.
#        return percentile_range(img_f, low, high)
#
#    p_low, p_high = np.percentile(masked_pixels, [low, high])
#    if (p_high - p_low) < 1e-6:
#        p_high = p_low + 1.0
#    return float(p_low), float(p_high)
#
#F e048c1f3680e5559d0c79d7f080629fecc161549 468 adept/core/algo/period.py
## Vendored into ADEPT on 2026-07-27.
## Source project: cell-period-estimator —
##   cell_period_estimator/core/period_core.py (vendored wholesale)
## Adaptations:
##   - Module vendored unchanged (pure NumPy/OpenCV, no Qt in the source).
##   - `choose_origin` was the source's (0, 0) stub; ADEPT M4-1 replaced it
##     with a real phase search (sub-sampled scan over [0, px) x [0, py),
##     ranked by the stacked cell's raw Laplacian variance).  The old
##     three-argument call still returns (0, 0) — `image` is opt-in.
##   - No other algorithmic changes.
#"""Period estimation core.
#
#Pure NumPy / OpenCV — no Qt imports here so the algorithms can be used
#headlessly (tests, batch processing) without a display server.
#
#The estimation strategy, per axis:
#
#1. Two 1-D projections are computed:
#   * an *intensity* projection (mean brightness along the other axis),
#     high-pass detrended to suppress slow illumination gradients, and
#   * a *gradient* projection (median of ``|Sobel|`` along the other axis).
#2. The period is estimated from the **intensity** projection.  The
#   fundamental dominates the intensity spectrum, which avoids the
#   half-period "edge doubling" that gradient projections suffer from
#   (every cell edge produces two gradient peaks).
#3. An rFFT picks the strongest peak inside the adaptive ``[lo, hi]``
#   search band to get a coarse candidate period.  A normalized
#   autocorrelation with parabolic sub-pixel interpolation cross-checks
#   and refines it, then applies harmonic correction.
#4. A modulation gate rejects nearly flat axes (e.g. the orthogonal axis
#   of a line/space pattern) so that noise normalized to unit scale is
#   not mistaken for a real period.
#"""
#
#from __future__ import annotations
#
#from dataclasses import dataclass, field
#from typing import List, Optional, Tuple
#
#import cv2
#import numpy as np
#
## An axis whose intensity projection has a standard deviation below this
## (in 8-bit grey levels) is considered featureless / not periodic.
#_MODULATION_STD_FLOOR = 0.5
#
#
#@dataclass
#class AxisSpectrum:
#    """FFT spectrum for a single axis, in *period* (not frequency) units."""
#
#    periods: np.ndarray
#    magnitude: np.ndarray
#    peak_period: Optional[float] = None
#
#    def normalized_magnitude(self) -> np.ndarray:
#        """Magnitude scaled to ``[0, 1]`` for plotting."""
#        mag = np.asarray(self.magnitude, dtype=np.float64)
#        if mag.size == 0:
#            return mag
#        peak = float(mag.max())
#        if peak <= 0:
#            return np.zeros_like(mag)
#        return mag / peak
#
#
#@dataclass
#class PeriodResult:
#    """Outcome of :func:`estimate_period`."""
#
#    px: Optional[int]
#    py: Optional[int]
#    confidence_x: float
#    confidence_y: float
#    axis_mode: str
#    peak_strength_x: float
#    peak_strength_y: float
#    spectrum_x: AxisSpectrum
#    spectrum_y: AxisSpectrum
#    candidates: List[Tuple[Optional[int], Optional[int]]] = field(default_factory=list)
#    warnings: List[str] = field(default_factory=list)
#
#
## --------------------------------------------------------------------------- #
## helpers
## --------------------------------------------------------------------------- #
#def _to_gray(image: np.ndarray) -> np.ndarray:
#    """Return a float64 single-channel copy of ``image``."""
#    arr = np.asarray(image)
#    if arr.ndim == 3:
#        if arr.shape[2] == 4:
#            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
#        else:
#            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
#    return arr.astype(np.float64)
#
#
#def _highpass(profile: np.ndarray, win: int) -> np.ndarray:
#    """Subtract an edge-padded moving average (high-pass detrend).
#
#    Edge padding avoids the spurious ramps a zero-padded average would
#    introduce at the profile boundaries.
#    """
#    n = profile.size
#    win = int(win)
#    if win < 3:
#        return profile - profile.mean()
#    if win % 2 == 0:
#        win += 1
#    win = min(win, n if n % 2 == 1 else n - 1)
#    if win < 3:
#        return profile - profile.mean()
#    pad = win // 2
#    padded = np.pad(profile, pad, mode="edge")
#    kernel = np.ones(win, dtype=np.float64) / win
#    moving = np.convolve(padded, kernel, mode="valid")
#    return profile - moving[: n]
#
#
#def _autocorr(x: np.ndarray) -> np.ndarray:
#    """Normalized autocorrelation (lag 0 == 1.0) for non-negative lags."""
#    x = x - x.mean()
#    n = x.size
#    full = np.correlate(x, x, mode="full")
#    ac = full[n - 1:]
#    if ac.size == 0 or ac[0] == 0:
#        return np.zeros_like(ac)
#    return ac / ac[0]
#
#
#def _parabolic(values: np.ndarray, idx: int) -> Tuple[float, float]:
#    """Sub-pixel peak location around integer index ``idx`` of ``values``."""
#    if idx <= 0 or idx >= values.size - 1:
#        return float(idx), float(values[idx])
#    ym1, y0, yp1 = values[idx - 1], values[idx], values[idx + 1]
#    denom = ym1 - 2.0 * y0 + yp1
#    if denom == 0:
#        return float(idx), float(y0)
#    delta = 0.5 * (ym1 - yp1) / denom
#    delta = float(np.clip(delta, -1.0, 1.0))
#    peak = y0 - 0.25 * (ym1 - yp1) * delta
#    return idx + delta, float(peak)
#
#
#def _search_band(min_period: Optional[int], max_period: Optional[int],
#                 length: int) -> Tuple[int, int]:
#    """Adaptive ``[lo, hi]`` period band for an axis of given length."""
#    lo = max(2, int(min_period) if min_period else 4)
#    hi = min(int(max_period) if max_period else length // 2, length // 2)
#    if hi < lo:
#        hi = lo
#    return lo, hi
#
#
#def _analyze_axis(intensity: np.ndarray, lo: int, hi: int,
#                  strength_threshold: float
#                  ) -> Tuple[Optional[int], float, float, AxisSpectrum, List[str]]:
#    """Estimate the period of one axis from its intensity projection.
#
#    Returns ``(period, confidence_0_100, peak_strength_0_1, spectrum,
#    warnings)``.  ``period`` is ``None`` when no reliable period is found.
#    """
#    warnings: List[str] = []
#    n = intensity.size
#    empty = AxisSpectrum(np.array([]), np.array([]), None)
#
#    if n < 8 or hi <= lo:
#        return None, 0.0, 0.0, empty, warnings
#
#    # Modulation gate: a nearly flat projection has no real period.
#    if float(intensity.std()) < _MODULATION_STD_FLOOR:
#        return None, 0.0, 0.0, empty, warnings
#
#    detrended = _highpass(intensity, max(3, n // 4))
#    detrended = detrended - detrended.mean()
#    if not np.any(detrended):
#        return None, 0.0, 0.0, empty, warnings
#
#    # --- rFFT: coarse candidate period --------------------------------- #
#    spectrum = np.abs(np.fft.rfft(detrended))
#    ks = np.arange(1, spectrum.size)
#    periods_all = n / ks
#    mags_all = spectrum[1:]
#    band = (periods_all >= lo) & (periods_all <= hi)
#    if not np.any(band):
#        return None, 0.0, 0.0, empty, warnings
#
#    band_periods = periods_all[band]
#    band_mags = mags_all[band]
#    order = np.argsort(band_periods)  # ascending period for a tidy spectrum
#    spec = AxisSpectrum(band_periods[order], band_mags[order], None)
#
#    p_fft = float(band_periods[np.argmax(band_mags)])
#
#    # --- autocorrelation: locate the fundamental period ---------------- #
#    # The intensity FFT peak can fall on a harmonic when the cell content
#    # is rich (a strong feature inside every cell repeats at sub-cell
#    # frequencies).  The autocorrelation is the more reliable arbiter of
#    # the *fundamental*: we pick the strongest local maximum in the lag
#    # band, which skips both the monotonic high-correlation region near
#    # lag 0 and the harmonic dips.
#    ac = _autocorr(detrended)
#
#    def ac_at(lag: float) -> float:
#        li = int(round(lag))
#        if 1 <= li < ac.size:
#            return float(ac[li])
#        return -1.0
#
#    lo_l = max(2, lo)
#    hi_l = min(ac.size - 2, hi)
#    if hi_l <= lo_l:
#        return None, 0.0, 0.0, spec, warnings
#
#    best_lag, best_val = None, -np.inf
#    for lag in range(lo_l, hi_l + 1):
#        if ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1] and ac[lag] > best_val:
#            best_lag, best_val = lag, ac[lag]
#    if best_lag is None:  # no clear peak; fall back to the FFT hint
#        best_lag = int(np.clip(round(p_fft), lo_l, hi_l))
#    period, strength = _parabolic(ac, best_lag)
#
#    # --- harmonic correction ------------------------------------------- #
#    p_int = int(round(period))
#    if ac_at(2 * period) > 1.15 * ac_at(period):
#        period = 2.0 * period
#        strength = ac_at(period)
#        warnings.append("doubled period (fundamental at 2x)")
#    elif p_int % 2 == 0 and ac_at(p_int // 2) >= 0.9 * ac_at(period):
#        period = period / 2.0
#        strength = ac_at(period)
#        warnings.append("halved period (sub-cell at p/2)")
#
#    period_int = int(round(period))
#    spec.peak_period = float(period_int)
#    strength = float(np.clip(strength, 0.0, 1.0))
#
#    if period_int < lo or strength < strength_threshold:
#        return None, round(strength * 100.0, 1), strength, spec, warnings
#
#    confidence = round(float(np.clip(strength, 0.0, 1.0)) * 100.0, 1)
#    return period_int, confidence, strength, spec, warnings
#
#
## --------------------------------------------------------------------------- #
## public API
## --------------------------------------------------------------------------- #
#def estimate_period(image: np.ndarray,
#                    min_period: Optional[int] = None,
#                    max_period: Optional[int] = None,
#                    strength_threshold: float = 0.18) -> PeriodResult:
#    """Estimate the repeating cell period of ``image``.
#
#    Parameters
#    ----------
#    image:
#        Greyscale or colour image (``np.ndarray``).
#    min_period, max_period:
#        Optional bounds on the period search, in pixels.  Defaults adapt
#        to the image size.
#    strength_threshold:
#        Minimum normalized autocorrelation strength (0..1) required to
#        accept a period on an axis.
#    """
#    gray = _to_gray(image)
#    h, w = gray.shape[:2]
#
#    # Intensity projections: mean brightness along the orthogonal axis.
#    prof_x = gray.mean(axis=0)   # varies along X, length == width
#    prof_y = gray.mean(axis=1)   # varies along Y, length == height
#
#    # Gradient projections (median |Sobel|) — computed per the spec; the
#    # period itself is taken from the intensity projection.
#    sob_x = np.abs(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3))
#    sob_y = np.abs(cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3))
#    _grad_x = np.median(sob_x, axis=0)
#    _grad_y = np.median(sob_y, axis=1)
#
#    lo_x, hi_x = _search_band(min_period, max_period, w)
#    lo_y, hi_y = _search_band(min_period, max_period, h)
#
#    px, conf_x, str_x, spec_x, warn_x = _analyze_axis(
#        prof_x, lo_x, hi_x, strength_threshold)
#    py, conf_y, str_y, spec_y, warn_y = _analyze_axis(
#        prof_y, lo_y, hi_y, strength_threshold)
#
#    has_x, has_y = px is not None, py is not None
#    if has_x and has_y:
#        axis_mode = "XY"
#    elif has_x:
#        axis_mode = "X"
#    elif has_y:
#        axis_mode = "Y"
#    else:
#        axis_mode = "NONE"
#
#    warnings = list(warn_x) + list(warn_y)
#    if axis_mode == "NONE":
#        warnings.append("no periodic structure detected")
#
#    candidates = _build_candidates(px, py, lo_x, hi_x, lo_y, hi_y)
#
#    return PeriodResult(
#        px=px, py=py,
#        confidence_x=conf_x, confidence_y=conf_y,
#        axis_mode=axis_mode,
#        peak_strength_x=str_x, peak_strength_y=str_y,
#        spectrum_x=spec_x, spectrum_y=spec_y,
#        candidates=candidates,
#        warnings=warnings,
#    )
#
#
#def _build_candidates(px: Optional[int], py: Optional[int],
#                      lo_x: int, hi_x: int, lo_y: int, hi_y: int
#                      ) -> List[Tuple[Optional[int], Optional[int]]]:
#    """Harmonic alternatives around the primary period for review."""
#    out: List[Tuple[Optional[int], Optional[int]]] = []
#    seen = set()
#
#    def x_ok(v):
#        return v is not None and lo_x <= v <= hi_x
#
#    def y_ok(v):
#        return v is not None and lo_y <= v <= hi_y
#
#    def add(a, b):
#        a = int(a) if a is not None else None
#        b = int(b) if b is not None else None
#        if a is not None and not x_ok(a):
#            return
#        if b is not None and not y_ok(b):
#            return
#        key = (a, b)
#        if key in seen or key == (None, None):
#            return
#        seen.add(key)
#        out.append(key)
#
#    add(px, py)
#    if px is not None:
#        add(px // 2, py)
#        add(2 * px, py)
#    if py is not None:
#        add(px, py // 2)
#        add(px, 2 * py)
#    if px is not None and py is not None:
#        add(px // 2, py // 2)
#        add(2 * px, 2 * py)
#    return out
#
#
#def _origin_axis_candidates(period: int, span: int, max_side: int) -> List[int]:
#    """Candidate origins along one axis (sub-sampled when ``period`` is big).
#
#    Returns ``[0]`` when fewer than two whole cells fit along the axis —
#    a single row/column of cells carries no phase information and some
#    offsets would leave no complete cell at all.
#    """
#    if span < 2 * period:
#        return [0]
#    step = 1 if period <= max_side else -(-period // max_side)  # ceil division
#    return list(range(0, period, step))
#
#
#def choose_origin(shape: Tuple[int, ...], px: Optional[int], py: Optional[int],
#                  image: Optional[np.ndarray] = None,
#                  method: str = "mean",
#                  max_evals: int = 256,
#                  refine: int = 2) -> Tuple[int, int]:
#    """Return the grid origin (top-left of the cell lattice) — phase search.
#
#    Convention
#    ----------
#    The returned ``(ox, oy)`` is the **lattice origin in pixels**, with
#    ``0 <= ox < px`` and ``0 <= oy < py``.  Feed it straight to the
#    ``origin=`` argument of :func:`adept.core.algo.golden.tile_coords` /
#    :func:`~adept.core.algo.golden.stack_cells`: cell ``(i, j)`` then
#    covers ``x in [ox + i*px, ox + (i+1)*px)`` and
#    ``y in [oy + j*py, oy + (j+1)*py)``.  Equivalently: cropping the
#    image so that it starts at ``(ox, oy)`` puts the lattice in phase,
#    after which every ``px`` / ``py`` pixels is a cell boundary.  Cells
#    that would run past the right/bottom border are dropped by
#    ``tile_coords``, so a larger origin simply wastes a little of the
#    image — it never shifts the answer's meaning.
#
#    What is optimised
#    -----------------
#    Each candidate origin is scored with
#    ``golden.ghosting_score(golden.stack_cells(...))[1]`` — the **raw
#    Laplacian variance** of the stacked cell.  **Higher is better**
#    (sharper stack = the cells landed on top of each other; a mis-phased
#    lattice smears structure across the cell border and the stack loses
#    contrast).  Ranking by the raw variance rather than the saturating
#    0..100 score matches :func:`golden.refine_period`; the 0..100 score
#    clips near the top and would lose the ordering.
#
#    ``method="mean"`` is used for scoring by default because the mean is
#    deliberately the phase-sensitive stack (the median hides small
#    misalignments), even when the caller later stacks with the median.
#
#    Search cost
#    -----------
#    The full grid is ``px * py`` offsets, which explodes for large
#    periods.  The scan is sub-sampled per axis so that at most
#    ``max_evals`` (~256) offsets are evaluated, then refined by a
#    ``±refine`` pixel neighbourhood scan around the coarse winner.
#
#    Guards (never raises, never returns an out-of-range origin)
#    ----------------------------------------------------------
#    ``image is None`` (backward-compatible call), ``px``/``py`` missing
#    or ``< 2``, a flat/constant image, or an image smaller than one cell
#    all return ``(0, 0)``.  An axis with fewer than two whole cells is
#    pinned to origin 0 (there is nothing to compare against).
#    """
#    from . import golden  # local import: keeps algo modules cycle-free
#
#    if image is None:
#        return (0, 0)
#    try:
#        px_i, py_i = int(px), int(py)   # type: ignore[arg-type]
#    except (TypeError, ValueError):
#        return (0, 0)
#    if px_i < 2 or py_i < 2:
#        return (0, 0)
#
#    gray = _to_gray(image)
#    if gray.ndim != 2 or gray.size == 0:
#        return (0, 0)
#    h, w = gray.shape[:2]
#    if h < py_i or w < px_i:          # not even one whole cell
#        return (0, 0)
#    if float(gray.std()) < 1e-6:      # flat image: every phase is identical
#        return (0, 0)
#
#    max_side = max(2, int(np.sqrt(max(int(max_evals), 4))))
#    xs = _origin_axis_candidates(px_i, w, max_side)
#    ys = _origin_axis_candidates(py_i, h, max_side)
#    if xs == [0] and ys == [0]:
#        return (0, 0)
#
#    def score(ox: int, oy: int) -> float:
#        stacked = golden.stack_cells(gray, px_i, py_i, method=method,
#                                     origin=(ox, oy))
#        return float(golden.ghosting_score(stacked)[1])
#
#    best_ox, best_oy, best_lv = 0, 0, -np.inf
#    for oy in ys:
#        for ox in xs:
#            lv = score(ox, oy)
#            if lv > best_lv:           # strict > → first winner wins (deterministic)
#                best_lv, best_ox, best_oy = lv, ox, oy
#
#    # Local refinement around the coarse winner (only where we sub-sampled).
#    refine = max(0, int(refine))
#    if refine and (len(xs) < px_i or len(ys) < py_i):
#        rx = [best_ox] if xs == [0] else [(best_ox + d) % px_i
#                                          for d in range(-refine, refine + 1)]
#        ry = [best_oy] if ys == [0] else [(best_oy + d) % py_i
#                                          for d in range(-refine, refine + 1)]
#        for oy in ry:
#            for ox in rx:
#                lv = score(ox, oy)
#                if lv > best_lv:
#                    best_lv, best_ox, best_oy = lv, ox, oy
#
#    return (int(best_ox) % px_i, int(best_oy) % py_i)
#
#F d8feeb2677bdd4f54b4fe3ffdd9ee9eeaf6c37e0 256 adept/core/algo/profile.py
## ADEPT algorithm library — authored 2026-07-29 (F7-11).
#"""一維投影定位：把影像壓成一條曲線，在曲線上找「轉折」，轉折之間就是一段結構。
#
#為什麼是找轉折，不是分材質
#--------------------------
#最初的想法是「EPI 暗、MG 中等、交界最亮 → 分三種灰階」。那對某一種 layout 是
#對的，但這個工具是泛用的：換一個 layer 就不是三種、也不一定誰亮誰暗，而且灰階
#本來就會隨機台與曝光漂移。**用絕對灰階分類，等於把一份 recipe 綁死在一種 layout
#和一台機台上。**
#
#轉折（曲線上斜率大的地方）沒有這個問題：它只問「哪裡在變」，不問「變成什麼」。
#幾種材質、誰亮誰暗都不用先知道，而使用者只要回答一個對任何 layout 都成立的
#問題 —— **「我要哪一段」**（包含中心的那一段、最寬的那一段、從左邊數第幾段）。
#
#為什麼在 ref 上做
#------------------
#test 上有一顆缺陷正在破壞結構，拿它找結構等於讓缺陷去干擾定位。ref 沒有缺陷，
#而且成對的 patch 本來就對齊，所以在 ref 上找到的位置直接可以用在 test 上。
#（這是卡片的預設值，不是這個模組的事 —— 這裡只管算。）
#
#什麼時候會失敗（很重要）
#------------------------
#patch 通常比一個重複單元還小，所以有些 patch 整張都落在同一種材質裡面，
#曲線是平的。那種 patch **不可能**定位 —— 它裡面就是沒有可以辨識的東西，
#這是資訊不夠，不是演算法不夠。
#
#但那種 patch 也**不需要**定位：整張都是同一種材質，整張量就是對的。
#所以 :func:`locate` 回報的 ``confidence`` 是給呼叫端做這個判斷用的 ——
#低於門檻就退回整張圖，並且**把那顆標記出來**，不要安靜地用一個沒對準的框去量。
#"""
#from __future__ import annotations
#
#from dataclasses import dataclass, field
#from typing import Any, List, Optional, Tuple
#
#import numpy as np
#
#__all__ = ["ProfileResult", "projection", "profile_confidence",
#           "find_transitions", "bands_from", "pick_band", "locate",
#           "distance_to_nearest_transition", "AXIS_X", "AXIS_Y", "PICK_RULES"]
#
##: ``axis="x"`` = 沿著 X 走的曲線（每一**欄**一個值），用來找垂直的結構邊界。
#AXIS_X = "x"
#AXIS_Y = "y"
#
##: 「我要哪一段」的規則。對任何 layout 都成立，不需要先知道有幾種材質。
#PICK_RULES = ("center", "widest", "darkest", "brightest", "index")
#
##: 「最陡的地方」至少要比「一般的地方」陡幾倍，才算這條曲線上有邊界。
##: 見 :func:`find_transitions` 裡的說明與實測數字。
#_MIN_PEAK_RATIO = 1.2
#
#
#@dataclass
#class ProfileResult:
#    """一次定位的完整結果 —— 包含**畫得出來**所需要的一切。
#
#    UI 的 panel 直接吃這個 dataclass（曲線、轉折線、選中的段），
#    所以「使用者看到的」跟「引擎算出來的」保證是同一份東西，不會兩邊走鐘。
#    """
#
#    axis: str
#    profile: np.ndarray                     # 平滑後的曲線（畫出來的就是這條）
#    raw: np.ndarray                         # 平滑前的曲線（淡色畫在後面當對照）
#    transitions: List[int] = field(default_factory=list)
#    bands: List[Tuple[int, int]] = field(default_factory=list)   # [start, end)
#    picked: Optional[Tuple[int, int]] = None
#    confidence: float = 0.0
#    #: 影像中心落在第幾段（畫 panel 時要標出來；找不到 = -1）
#    center_band: int = -1
#
#    @property
#    def length(self) -> int:
#        return int(self.profile.size)
#
#
#def _smooth(values: np.ndarray, window: int) -> np.ndarray:
#    """一維移動平均。雜訊不先壓掉的話，梯度上到處都是假的轉折。"""
#    w = max(1, int(window))
#    if w <= 1 or values.size == 0:
#        return values.astype(np.float32, copy=True)
#    if w % 2 == 0:
#        w += 1
#    pad = w // 2
#    padded = np.pad(values.astype(np.float32), pad, mode="edge")
#    kernel = np.ones(w, dtype=np.float32) / float(w)
#    return np.convolve(padded, kernel, mode="valid").astype(np.float32)
#
#
#def projection(img: Any, axis: str = AXIS_X, smooth: int = 3) -> Tuple[np.ndarray, np.ndarray]:
#    """把影像壓成一條曲線。回傳 ``(平滑後, 原始)``。
#
#    ``axis="x"``：每一欄取平均（曲線長度 = 影像寬度），用來找**垂直**的邊界。
#    ``axis="y"``：每一列取平均，用來找水平的邊界。
#
#    取**平均**而不是中位數是刻意的：這裡要的是「材質的整體亮度」，
#    而缺陷只佔一欄裡的幾個像素，對平均的影響很小；反而中位數會把
#    「一欄裡有一半是另一種材質」這種真實的轉折壓掉。
#    """
#    a = np.asarray(img, dtype=np.float32)
#    if a.ndim == 3:
#        a = a.mean(axis=2)
#    if a.ndim != 2 or a.size == 0:
#        empty = np.zeros(0, dtype=np.float32)
#        return empty, empty
#    raw = a.mean(axis=0) if str(axis) == AXIS_X else a.mean(axis=1)
#    return _smooth(raw, smooth), raw.astype(np.float32)
#
#
#def profile_confidence(smoothed: np.ndarray, raw: np.ndarray) -> float:
#    """「這條曲線上有多少是真的結構，而不是雜訊」。
#
#    定義是 ``曲線的起伏 / 雜訊的尺度``：分子取平滑後曲線的標準差，
#    分母取「平滑前減平滑後」的**穩健**尺度（MAD，不是標準差）。
#
#    為什麼分母要用 MAD
#    ------------------
#    銳利的邊界會讓平滑吃掉一點真訊號，那幾格的殘差很大。用標準差當分母，
#    邊界越銳利、分母被灌得越大 —— 結果是「結構越清楚、信心越低」，完全相反。
#    MAD 只看中位數附近，那幾格灌不進去。
#
#    量過的實際數字（合成與真實 patch 都試過）：整張同一種材質約 **0.7**，
#    任何有結構的情況都在 **20 以上**，中間差了一個數量級 ——
#    所以門檻放在個位數就分得很開，不需要逐個 layer 調。
#
#    注意它問的**不是**「有沒有邊界」，是「有沒有訊號」。一片平緩的亮度漸層
#    信心也會很高（那確實是訊號），但它一條邊界都沒有 ——
#    那種情況由「找不到轉折」那條路處理，而漸層本身該交給 Enhance 的
#    背景平坦化卡去除。
#    """
#    sm = np.asarray(smoothed, dtype=np.float32)
#    rw = np.asarray(raw, dtype=np.float32)
#    if sm.size == 0 or rw.size != sm.size:
#        return 0.0
#    resid = rw - sm
#    med = float(np.median(resid))
#    mad = 1.4826 * float(np.median(np.abs(resid - med)))
#    return float(np.std(sm)) / max(mad, 1e-6)
#
#
#def find_transitions(profile: np.ndarray, sensitivity: float = 0.35,
#                     min_gap: int = 4) -> List[int]:
#    """找曲線上的轉折（回傳位置清單）。
#
#    ``sensitivity`` 0–1：要多陡才算一個轉折，**相對於這條曲線上最陡的地方**。
#    用相對值而不是絕對灰階，是為了讓同一個設定換一個 layer、換一台機台還能用。
#
#    ``min_gap`` 是兩個轉折至少要隔多遠（像素）—— 一個邊界在梯度上會佔好幾格，
#    沒有這個的話一條邊界會被算成好幾條。
#
#    局部極大用的是 ``g[i] > g[i-1]``（嚴格大於）而不是 ``>=``：一段**固定斜率**
#    的漸層上每一格的梯度都相等，用 ``>=`` 會把整段都判成轉折。
#    """
#    p = np.asarray(profile, dtype=np.float32)
#    if p.size < 3:
#        return []
#    grad = np.abs(np.gradient(p))
#    peak = float(grad.max())
#    if peak <= 0.0:
#        return []
#
#    # 「最陡的地方」必須真的比「一般的地方」陡，否則這條曲線上根本沒有邊界。
#    # 固定斜率的漸層每一格梯度都相等（比值 = 1.00），剩下的差異只是浮點誤差 ——
#    # 沒有這一關的話，浮點誤差會決定邊界畫在哪，而且每一格都會被判成邊界。
#    # 量過的比值：漸層 1.00、正弦 1.41、方波 極大 —— 門檻放 1.2 兩邊都安全。
#    if peak < _MIN_PEAK_RATIO * max(float(np.median(grad)), 1e-9):
#        return []
#
#    thr = float(np.clip(sensitivity, 0.0, 1.0)) * peak
#    gap = max(1, int(min_gap))
#
#    cand = [i for i in range(1, p.size - 1)
#            if grad[i] >= thr and grad[i] > grad[i - 1] and grad[i] >= grad[i + 1]]
#    cand.sort(key=lambda i: -grad[i])       # 強的先佔位
#    kept: List[int] = []
#    for i in cand:
#        if all(abs(i - j) >= gap for j in kept):
#            kept.append(i)
#    return sorted(kept)
#
#
#def bands_from(transitions: List[int], length: int) -> List[Tuple[int, int]]:
#    """轉折之間就是一段。影像的兩端也算邊界（半段仍然是段）。"""
#    if length <= 0:
#        return []
#    edges = [0] + [int(t) for t in sorted(transitions) if 0 < int(t) < length] + [int(length)]
#    out: List[Tuple[int, int]] = []
#    for a, b in zip(edges, edges[1:]):
#        if b > a:
#            out.append((int(a), int(b)))
#    return out
#
#
#def _band_level(profile: np.ndarray, band: Tuple[int, int]) -> float:
#    a, b = band
#    seg = profile[a:b]
#    return float(seg.mean()) if seg.size else 0.0
#
#
#def pick_band(bands: List[Tuple[int, int]], profile: np.ndarray,
#              rule: str = "center", index: int = 0) -> Optional[Tuple[int, int]]:
#    """依規則挑一段。``center`` 是預設 —— 缺陷永遠在 patch 正中央。"""
#    if not bands:
#        return None
#    rule = str(rule)
#    if rule == "widest":
#        return max(bands, key=lambda b: b[1] - b[0])
#    if rule == "darkest":
#        return min(bands, key=lambda b: _band_level(profile, b))
#    if rule == "brightest":
#        return max(bands, key=lambda b: _band_level(profile, b))
#    if rule == "index":
#        i = int(index)
#        return bands[i] if -len(bands) <= i < len(bands) else None
#    mid = profile.size / 2.0            # center（預設）
#    for a, b in bands:
#        if a <= mid < b:
#            return (a, b)
#    return None
#
#
#def locate(img: Any, axis: str = AXIS_X, sensitivity: float = 0.35,
#           smooth: int = 3, min_gap: int = 4, rule: str = "center",
#           index: int = 0) -> ProfileResult:
#    """一次做完：投影 → 找轉折 → 分段 → 挑一段。
#
#    這是 step 卡與 UI panel 共用的唯一入口 —— 兩邊看到的必須是同一次計算，
#    不然「畫面上的框」跟「真的量下去的框」會不一樣，而那種 bug 很難發現。
#    """
#    prof, raw = projection(img, axis=axis, smooth=smooth)
#    if prof.size == 0:
#        return ProfileResult(axis=str(axis), profile=prof, raw=raw)
#
#    trans = find_transitions(prof, sensitivity=sensitivity, min_gap=min_gap)
#    conf = profile_confidence(prof, raw)
#    bands = bands_from(trans, int(prof.size))
#    picked = pick_band(bands, prof, rule=rule, index=index)
#
#    mid = prof.size / 2.0
#    center_band = next((i for i, (a, b) in enumerate(bands) if a <= mid < b), -1)
#    return ProfileResult(axis=str(axis), profile=prof, raw=raw,
#                         transitions=trans, bands=bands, picked=picked,
#                         confidence=float(conf), center_band=center_band)
#
#
#def distance_to_nearest_transition(res: ProfileResult) -> float:
#    """影像中心（= 缺陷）離最近的一條轉折有多遠，單位是像素。
#
#    這個數字本身就是一個特徵：缺陷落在結構正中間，跟落在兩種材質的交界上，
#    通常不是同一回事。沒有任何轉折時回 ``inf``（呼叫端自行決定怎麼記）。
#    """
#    if not res.transitions:
#        return float("inf")
#    mid = res.profile.size / 2.0
#    return float(min(abs(mid - t) for t in res.transitions))
#
#F c8a612c072ba3616d22e6f7b2ae7238bd454c835 137 adept/core/algo/quality.py
## Vendored into ADEPT on 2026-07-27.
## Source project: MMH
##   - src/core/image_quality.py          (check_lap_quality, DEFAULT_LAP_THRESHOLD)
##   - tools/image_quality_checker.py     (pure block ~lines 46-97: _load_gray,
##     compute_quality — Qt GUI/worker code NOT vendored)
## Adaptations:
##   - ZERO Qt: only the pure metric functions were extracted from the
##     image_quality_checker tool.
##   - `compute_quality` now accepts EITHER a np.ndarray (grayscale or
##     colour) OR a filesystem path; paths are loaded with a CJK-safe
##     np.fromfile + cv2.imdecode inline (the source used cv2.imread,
##     which fails on non-ASCII paths on Windows).
##   - `_load_gray` kept as a private helper, rewritten around the CJK-safe
##     decode; grayscale conversion / uint8 normalization behavior kept.
##   - No changes to the metric math (Laplacian variance, Tenengrad,
##     FFT high-frequency ratio) or to check_lap_quality.
#"""Image quality screening for SEM images.
#
#Primary metric: Laplacian variance after medianBlur(5).
#  - medianBlur removes salt-and-pepper / shot noise so isolated pixels are
#    not mistaken for genuine high-frequency edges.
#  - Laplacian variance reflects true edge sharpness across the image.
#
#`compute_quality` additionally reports Tenengrad (mean squared Sobel
#gradient) and the FFT high-frequency ratio (fraction of spectral energy
#outside the inner 35 % radius).
#
#Typical PASS thresholds for well-focused SEM images:
#  Laplacian var  >  100   (adjust to your magnification / pixel size)
#  Tenengrad      > 1000   (optional)
#  FFT HF ratio   >  0.05  (optional)
#"""
#
#from __future__ import annotations
#
#from typing import Optional, Union
#
#import cv2
#import numpy as np
#
#DEFAULT_LAP_THRESHOLD: float = 145.0
#
#
#def check_lap_quality(img: np.ndarray) -> float:
#    """Return Laplacian variance of *img* after median pre-filtering.
#
#    Parameters
#    ----------
#    img : uint8 grayscale ndarray
#
#    Returns
#    -------
#    float
#        Laplacian variance; higher = sharper. Compare against a threshold
#        (e.g. DEFAULT_LAP_THRESHOLD) to decide PASS/FAIL.
#    """
#    denoised = cv2.medianBlur(img, 5)
#    lap = cv2.Laplacian(denoised.astype(np.float64), cv2.CV_64F)
#    return float(lap.var())
#
#
#def _to_gray_u8(img: np.ndarray) -> np.ndarray:
#    """Coerce an ndarray to uint8 single-channel grayscale."""
#    if img.ndim == 3:
#        if img.shape[2] == 4:
#            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
#        else:
#            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#    if img.dtype != np.uint8:
#        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
#    return img
#
#
#def _load_gray(path: str) -> Optional[np.ndarray]:
#    """Load *path* as uint8 grayscale, CJK-path safe. None on failure."""
#    try:
#        data = np.fromfile(str(path), dtype=np.uint8)
#    except (OSError, IOError):
#        return None
#    if data.size == 0:
#        return None
#    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
#    if img is None:
#        return None
#    return _to_gray_u8(img)
#
#
#def compute_quality(image: Union[np.ndarray, str]) -> dict:
#    """Return dict with laplacian_var, tenengrad, fft_hf_ratio (all float).
#
#    ``image`` may be a np.ndarray (grayscale or colour) or a filesystem
#    path (str / os.PathLike); paths are loaded CJK-safely via
#    np.fromfile + cv2.imdecode.
#    """
#    if isinstance(image, np.ndarray):
#        img = _to_gray_u8(image)
#    else:
#        img = _load_gray(str(image))
#    if img is None:
#        return {"error": "Cannot load image", "laplacian_var": 0.0,
#                "tenengrad": 0.0, "fft_hf_ratio": 0.0}
#
#    # Pre-process: median blur (ksize=5) to suppress salt-and-pepper noise
#    # before sharpness metrics are evaluated — avoids noise being mistaken
#    # for genuine high-frequency edge content.
#    img = cv2.medianBlur(img, 5)
#
#    # 1. Laplacian variance
#    lap = cv2.Laplacian(img.astype(np.float64), cv2.CV_64F)
#    laplacian_var = float(lap.var())
#
#    # 2. Tenengrad (Sobel-based)
#    gx = cv2.Sobel(img.astype(np.float64), cv2.CV_64F, 1, 0, ksize=3)
#    gy = cv2.Sobel(img.astype(np.float64), cv2.CV_64F, 0, 1, ksize=3)
#    tenengrad = float(np.mean(gx**2 + gy**2))
#
#    # 3. FFT high-frequency ratio (outer spectrum energy)
#    h, w = img.shape
#    fft = np.fft.fft2(img.astype(np.float64))
#    fft_shift = np.fft.fftshift(fft)
#    mag = np.abs(fft_shift)
#    cy, cx = h // 2, w // 2
#    # inner radius = 35 % of half-diagonal → keeps DC and low-freq
#    r_inner = min(cy, cx) * 0.35
#    ys, xs = np.ogrid[:h, :w]
#    dist = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
#    total_energy = float(mag.sum()) + 1e-9
#    hf_energy = float(mag[dist > r_inner].sum())
#    fft_hf_ratio = hf_energy / total_energy
#
#    return {
#        "laplacian_var": laplacian_var,
#        "tenengrad":     tenengrad,
#        "fft_hf_ratio":  fft_hf_ratio,
#        "error":         "",
#    }
#
#F a9735c3dcf54c6115467af9b4bc3f21838fe58d0 438 adept/core/algo/roi.py
## ---------------------------------------------------------------------------
## Vendored into ADEPT on 2026-07-27.
## Source project: Perspective-Combination (Fusi3)
## Source file:    perscomb/core/roi_set.py (vendored wholesale)
## Adaptations:
##   - Added pixel_rect_to_norm(rect, shape) helper (inverse of
##     NamedROI.to_pixel_rect) for pixel-rect -> normalized-rect conversion.
##   - Note: the pixel-space ROIRegion dataclass from ebeam_snr.py is
##     intentionally NOT vendored; in ADEPT pixel rects are plain
##     (x, y, w, h) tuples (see adept.core.algo.snr.roi_snr).
##   - Algorithm behavior unchanged.
## ---------------------------------------------------------------------------
#"""ROI data model for multi-ROI analysis across Landing Energy images.
#
#Normalized-coordinate ROIs (NamedROI.norm_rect, all components in [0, 1])
#are the canonical representation. Pixel-space rects are plain (x, y, w, h)
#tuples; the pixel-space ROIRegion dataclass from the source project's
#ebeam_snr module is intentionally not vendored.
#
#Classes:
#    NamedROI        – A single named bounding-box ROI (normalized coordinates).
#    MultiROISet     – Ordered collection of NamedROIs with management helpers.
#    ROIStats        – Per-ROI pixel statistics extracted from one image.
#    ROIImageLayer   – All ROI stats for one image (base / compare / diff).
#    ROISNREntry     – SNR and supporting values for one diff image.
#    ROIFullResult   – Complete cross-layer statistics + derived SNR per LE.
#"""
#from __future__ import annotations
#
#import uuid
#from dataclasses import dataclass, field
#from typing import Dict, List, Literal, Optional, Tuple
#
#import numpy as np
#
#
## ---------------------------------------------------------------------------
## Colour constants for ROI drawing (BGR tuples)
## ---------------------------------------------------------------------------
#_REFERENCE_COLOR: Tuple[int, int, int] = (255, 255, 0)   # cyan (BGR)
#_TARGET_COLOR: Tuple[int, int, int] = (0, 0, 255)         # red (BGR)
#
#
## ---------------------------------------------------------------------------
## Helpers
## ---------------------------------------------------------------------------
#
#def pixel_rect_to_norm(
#    rect: Tuple[int, int, int, int],
#    shape: Tuple[int, int],
#) -> Tuple[float, float, float, float]:
#    """Convert a pixel-space (x, y, w, h) rect to a normalized (nx, ny, nw, nh).
#
#    Inverse of :meth:`NamedROI.to_pixel_rect` for *shape* = (H, W): the rect
#    is first clamped to the image bounds (origin clamped into the image, size
#    clamped to at least 1 px and to the remaining extent), then divided by the
#    image dimensions.
#    """
#    h, w = shape[:2]
#    x, y, rw, rh = rect
#    x = max(0, min(int(x), w - 1))
#    y = max(0, min(int(y), h - 1))
#    rw = max(1, min(int(rw), w - x))
#    rh = max(1, min(int(rh), h - y))
#    return (x / w, y / h, rw / w, rh / h)
#
#
## ---------------------------------------------------------------------------
## Core data structures
## ---------------------------------------------------------------------------
#
#@dataclass
#class NamedROI:
#    """A single bounding-box ROI in normalized image coordinates.
#
#    Attributes
#    ----------
#    id          : Unique identifier (auto-generated UUID4 short string).
#    label       : Human-readable name shown in the UI (e.g. "ROI_001").
#    roi_type    : 'target' (defect of interest) or 'reference' (background).
#    color_bgr   : BGR colour used for drawing this ROI on images.
#    norm_rect   : (nx, ny, nw, nh) all in [0, 1], measured on the BASE image.
#    """
#    id: str
#    label: str
#    roi_type: Literal['target', 'reference']
#    color_bgr: Tuple[int, int, int]
#    norm_rect: Tuple[float, float, float, float]   # (nx, ny, nw, nh)
#
#    def to_pixel_rect(self, img_shape: Tuple[int, int]) -> Tuple[int, int, int, int]:
#        """Convert norm_rect to (x, y, w, h) integer pixels for *img_shape* (H, W)."""
#        h, w = img_shape[:2]
#        nx, ny, nw, nh = self.norm_rect
#        x = int(round(nx * w))
#        y = int(round(ny * h))
#        pw = max(1, int(round(nw * w)))
#        ph = max(1, int(round(nh * h)))
#        # Clamp to image bounds
#        x = max(0, min(x, w - 1))
#        y = max(0, min(y, h - 1))
#        pw = min(pw, w - x)
#        ph = min(ph, h - y)
#        return x, y, pw, ph
#
#    def crop(self, img: np.ndarray) -> np.ndarray:
#        """Return the pixel region of *img* corresponding to this ROI."""
#        x, y, pw, ph = self.to_pixel_rect(img.shape)
#        return img[y:y + ph, x:x + pw]
#
#
#@dataclass
#class ROIStats:
#    """Pixel statistics for one ROI extracted from one image."""
#    mean: float
#    std: float
#    p2: float
#    p98: float
#    median: float
#    pixel_count: int
#
#    @classmethod
#    def from_pixels(cls, pixels: np.ndarray) -> "ROIStats":
#        f = pixels.astype(np.float32).ravel()
#        if f.size == 0:
#            return cls(mean=0.0, std=0.0, p2=0.0, p98=0.0, median=0.0, pixel_count=0)
#        p2, p98 = float(np.percentile(f, 2)), float(np.percentile(f, 98))
#        return cls(
#            mean=float(np.mean(f)),
#            std=float(np.std(f)),
#            p2=p2,
#            p98=p98,
#            median=float(np.median(f)),
#            pixel_count=int(f.size),
#        )
#
#
#@dataclass
#class ROIImageLayer:
#    """All ROI stats extracted from a single image.
#
#    Attributes
#    ----------
#    image_label : Human-readable identifier, e.g. "base", "LE1_compare", "LE1_diff".
#    layer_type  : Category of the image.
#    roi_stats   : Mapping from roi.id → ROIStats.
#    """
#    image_label: str
#    layer_type: Literal['base', 'compare', 'diff']
#    roi_stats: Dict[str, ROIStats] = field(default_factory=dict)
#
#
#@dataclass
#class ROISNREntry:
#    """SNR and supporting values for one diff image."""
#    le_label: str
#    snr: float
#    mu_target: float
#    mu_ref: float
#    sigma_ref: float
#
#
#@dataclass
#class ROIFullResult:
#    """Complete cross-layer ROI analysis result.
#
#    Attributes
#    ----------
#    roi_set            : The MultiROISet used for this computation.
#    layers             : [base layer] + [compare layers…] + [diff layers…]
#    snr_per_diff       : SNR computed from diff layers, keyed by LE label.
#    snr_per_compare    : SNR computed from normalized compare layers, keyed by LE
#                         label.  Measures the compare image's own defect visibility
#                         after being mapped through the base anchor — useful for
#                         quantifying clip-induced SNR degradation in cross-LE
#                         normalization (GLV Mask / Percentile).
#    raw_snr_base       : SNR of the raw (un-normalized) base image using the same
#                         target/reference formula.  Comparing this to the base-layer
#                         SNR (normalized) shows how much normalization alone changes
#                         the base image's defect visibility.
#    normalize_method   : The normalization method that was applied.
#    nonlinear_warning  : True when HEQ/CLAHE was used (stats not cross-LE comparable).
#    """
#    roi_set: "MultiROISet"
#    layers: List[ROIImageLayer] = field(default_factory=list)
#    snr_per_diff: Dict[str, ROISNREntry] = field(default_factory=dict)
#    snr_per_compare: Dict[str, ROISNREntry] = field(default_factory=dict)
#    raw_snr_base: Optional[ROISNREntry] = None   # SNR on raw (un-normalized) base
#    normalize_method: str = 'percentile'
#    nonlinear_warning: bool = False
#
#    # Convenience accessors -------------------------------------------------
#
#    def get_layer(self, image_label: str) -> Optional[ROIImageLayer]:
#        for layer in self.layers:
#            if layer.image_label == image_label:
#                return layer
#        return None
#
#    def get_base_layer(self) -> Optional[ROIImageLayer]:
#        for layer in self.layers:
#            if layer.layer_type == 'base':
#                return layer
#        return None
#
#    def compare_labels(self) -> List[str]:
#        return [l.image_label for l in self.layers if l.layer_type == 'compare']
#
#    def diff_labels(self) -> List[str]:
#        return [l.image_label for l in self.layers if l.layer_type == 'diff']
#
#
## ---------------------------------------------------------------------------
## MultiROISet
## ---------------------------------------------------------------------------
#
#class MultiROISet:
#    """Ordered collection of NamedROIs drawn on the BASE image.
#
#    Rules
#    -----
#    - At most ONE ROI may have roi_type == 'target' at any time.
#    - set_target(id) demotes the previous target to 'reference' automatically.
#    - All reference ROIs use _REFERENCE_COLOR (cyan); the target always uses
#      _TARGET_COLOR (red).
#    """
#
#    def __init__(self) -> None:
#        self._rois: List[NamedROI] = []
#
#    # ------------------------------------------------------------------
#    # CRUD
#    # ------------------------------------------------------------------
#
#    def add_roi(
#        self,
#        norm_rect: Tuple[float, float, float, float],
#        label: Optional[str] = None,
#        roi_type: Literal['target', 'reference'] = 'reference',
#    ) -> str:
#        """Add a new ROI and return its id.
#
#        If *roi_type* is 'target', any existing target is demoted automatically.
#        """
#        roi_id = uuid.uuid4().hex[:8]
#        if label is None:
#            label = f"ROI_{len(self._rois) + 1:03d}"
#
#        if roi_type == 'target':
#            self._demote_current_target()
#            color = _TARGET_COLOR
#        else:
#            color = _REFERENCE_COLOR
#
#        roi = NamedROI(
#            id=roi_id,
#            label=label,
#            roi_type=roi_type,
#            color_bgr=color,
#            norm_rect=norm_rect,
#        )
#        self._rois.append(roi)
#        return roi_id
#
#    def remove_roi(self, roi_id: str) -> bool:
#        """Remove ROI by id. Returns True if found and removed."""
#        before = len(self._rois)
#        self._rois = [r for r in self._rois if r.id != roi_id]
#        return len(self._rois) < before
#
#    def clear(self) -> None:
#        self._rois.clear()
#
#    def shifted(self, dx: int, dy: int, ref_shape: Tuple[int, int]) -> "MultiROISet":
#        """Return a copy of this ROISet with every ROI translated by (dx, dy) pixels.
#
#        Used to remap ROI coordinates from one base image's coordinate space to
#        another when the alignment offset between the two bases is known.
#
#        Parameters
#        ----------
#        dx, dy  : Pixel shift in the horizontal / vertical direction.
#                  Positive dx moves the ROI right; positive dy moves it down.
#        ref_shape : (H, W) of the *reference* base image on which the original
#                    norm_rect values are defined.  Used to convert the pixel
#                    shift to normalised [0, 1] offsets.
#        """
#        import copy as _copy
#        h, w = ref_shape[:2]
#        new_set = MultiROISet()
#        for roi in self._rois:
#            nx, ny, nw, nh = roi.norm_rect
#            new_nx = nx + dx / w
#            new_ny = ny + dy / h
#            # Clamp so the ROI stays within [0, 1] while preserving size
#            new_nx = max(0.0, min(1.0 - nw, new_nx))
#            new_ny = max(0.0, min(1.0 - nh, new_ny))
#            new_roi = _copy.copy(roi)
#            new_roi.norm_rect = (new_nx, new_ny, nw, nh)
#            new_set._rois.append(new_roi)
#        return new_set
#
#    def update_rect(self, roi_id: str, norm_rect: Tuple[float, float, float, float]) -> bool:
#        """Update the norm_rect of an existing ROI. Returns True if found."""
#        for roi in self._rois:
#            if roi.id == roi_id:
#                roi.norm_rect = norm_rect
#                return True
#        return False
#
#    # ------------------------------------------------------------------
#    # Target management
#    # ------------------------------------------------------------------
#
#    def set_target(self, roi_id: str) -> bool:
#        """Promote *roi_id* to target; demote any existing target. Returns True if found."""
#        roi = self._get_by_id(roi_id)
#        if roi is None:
#            return False
#        self._demote_current_target()
#        roi.roi_type = 'target'
#        roi.color_bgr = _TARGET_COLOR
#        return True
#
#    def set_reference(self, roi_id: str) -> bool:
#        """Force *roi_id* to reference type."""
#        roi = self._get_by_id(roi_id)
#        if roi is None:
#            return False
#        roi.roi_type = 'reference'
#        roi.color_bgr = _REFERENCE_COLOR
#        return True
#
#    def get_target(self) -> Optional[NamedROI]:
#        for roi in self._rois:
#            if roi.roi_type == 'target':
#                return roi
#        return None
#
#    def get_references(self) -> List[NamedROI]:
#        return [r for r in self._rois if r.roi_type == 'reference']
#
#    # ------------------------------------------------------------------
#    # Grid generation (Multi-Add)
#    # ------------------------------------------------------------------
#
#    def generate_grid(
#        self,
#        anchor_tl_norm: Tuple[float, float],
#        anchor_br_norm: Tuple[float, float],
#        cols: int,
#        rows: int,
#        roi_w_px: int,
#        roi_h_px: int,
#        img_shape: Tuple[int, int],
#    ) -> List[Tuple[float, float, float, float]]:
#        """Generate a regular cols×rows grid of norm_rects between two anchor points.
#
#        Anchors define the centers of the top-left and bottom-right corner ROIs.
#        The spacing between ROIs is derived from the anchor span divided by (count-1),
#        so exactly `cols × rows` ROIs are produced filling the anchor area evenly.
#        All returned rects are in normalized [0, 1] coordinates.
#        The rois are NOT added to the set here — caller must call add_roi() for each.
#
#        Parameters
#        ----------
#        anchor_tl_norm  : (norm_cx, norm_cy) center of top-left corner ROI.
#        anchor_br_norm  : (norm_cx, norm_cy) center of bottom-right corner ROI.
#        cols            : Number of ROIs in the horizontal direction.
#        rows            : Number of ROIs in the vertical direction.
#        roi_w_px        : Width of each ROI (pixels).
#        roi_h_px        : Height of each ROI (pixels).
#        img_shape       : (H, W) of the base image for pixel↔norm conversion.
#        """
#        h, w = img_shape[:2]
#        if w == 0 or h == 0:
#            return []
#        cols = max(1, int(cols))
#        rows = max(1, int(rows))
#
#        # Convert anchor centers to pixel coordinates
#        tl_cx = anchor_tl_norm[0] * w
#        tl_cy = anchor_tl_norm[1] * h
#        br_cx = anchor_br_norm[0] * w
#        br_cy = anchor_br_norm[1] * h
#
#        # Pixel-space ROI size in norm coords
#        nw = roi_w_px / w
#        nh = roi_h_px / h
#
#        # Step between ROI centers derived from span / (count-1)
#        step_x = (br_cx - tl_cx) / (cols - 1) if cols > 1 else 0.0
#        step_y = (br_cy - tl_cy) / (rows - 1) if rows > 1 else 0.0
#
#        rects: List[Tuple[float, float, float, float]] = []
#        for r in range(rows):
#            for c in range(cols):
#                cx = tl_cx + c * step_x
#                cy = tl_cy + r * step_y
#                # Top-left corner of ROI in norm coords
#                nx = max(0.0, min((cx - roi_w_px / 2.0) / w, 1.0 - nw))
#                ny = max(0.0, min((cy - roi_h_px / 2.0) / h, 1.0 - nh))
#                rects.append((nx, ny, nw, nh))
#
#        return rects
#
#    # ------------------------------------------------------------------
#    # Accessors
#    # ------------------------------------------------------------------
#
#    @property
#    def rois(self) -> List[NamedROI]:
#        return list(self._rois)
#
#    def __len__(self) -> int:
#        return len(self._rois)
#
#    def __bool__(self) -> bool:
#        return bool(self._rois)
#
#    def get_by_id(self, roi_id: str) -> Optional[NamedROI]:
#        return self._get_by_id(roi_id)
#
#    # ------------------------------------------------------------------
#    # Private helpers
#    # ------------------------------------------------------------------
#
#    def _get_by_id(self, roi_id: str) -> Optional[NamedROI]:
#        for roi in self._rois:
#            if roi.id == roi_id:
#                return roi
#        return None
#
#    def _demote_current_target(self) -> None:
#        for roi in self._rois:
#            if roi.roi_type == 'target':
#                roi.roi_type = 'reference'
#                roi.color_bgr = _REFERENCE_COLOR
#
#F ac1c581984cef7d1af53288415f759fb8006172f 327 adept/core/algo/snr.py
## ---------------------------------------------------------------------------
## Vendored into ADEPT on 2026-07-27.
## Source projects/files:
##   - PEAR: pear/core/attributes.py (snr -> snr_signed, the canonical
##     e-beam SNR primitive)
##   - Perspective-Combination (Fusi3): perscomb/core/ebeam_snr.py
##     (calculate_roi_snr -> roi_snr)
##   - Perspective-Combination (Fusi3): perscomb/core/perspective_combine.py
##     (compute_snr_map, _center_gaussian_mask -> center_gaussian_mask)
## Adaptations (agreed friction fixes):
##   - snr_signed(target_pixels, ref_pixels) vendored from PEAR as the single
##     canonical SNR primitive: (mean_target - mean_ref) / std_ref, signed.
##     Other modules must reference this function rather than re-deriving it.
##   - roi_snr takes a plain pixel rect (x, y, w, h) tuple instead of the
##     ebeam_snr.ROIRegion dataclass (intentionally not vendored) and returns
##     a RoiSnrResult dataclass instead of a dict. It reports BOTH the signed
##     SNR (via the snr_signed primitive) and the absolute SNR (snr_abs, the
##     original dict's 'snr' value); all other statistics keep the original
##     formulas (contrast, contrast_ratio, edge_sharpness, dvi are computed
##     exactly as before, with dvi based on the absolute SNR).
##   - compute_snr_map originally returned an undocumented (uint8_map, raw_max)
##     tuple despite an ndarray annotation. It now returns a SnrMapResult
##     dataclass: map_float is the normalized float32 map in [0, 1] (the same
##     values the old uint8 map encoded, before the *255 quantization) and
##     snr_max is the raw pre-normalization SNR maximum. .to_uint8() reproduces
##     the old uint8 output exactly. window_size / clip_sigma / clip_percentile
##     / exclude_border parameters and behavior are unchanged.
##   - Algorithm behavior otherwise unchanged.
## ---------------------------------------------------------------------------
#"""SNR metrics for e-beam defect imaging.
#
#Canonical SNR definition (PEAR): ``(mean_target - mean_reference) /
#std_reference`` — signed, so a defect darker than its background yields a
#negative SNR. :func:`snr_signed` is the single canonical primitive; every
#other SNR in this package derives from it.
#"""
#from __future__ import annotations
#
#from dataclasses import dataclass
#from typing import Optional, Tuple
#
#import cv2
#import numpy as np
#
#_EPS = 1e-9
#
#
#def snr_signed(target_pixels: np.ndarray, ref_pixels: np.ndarray) -> float:
#    """E-beam SNR: ``(mean_target - mean_reference) / std_reference``.
#
#    The canonical signed SNR primitive (PEAR definition). Returns 0.0 when
#    either pixel set is empty or the reference is flat (std < 1e-9).
#    """
#    t = np.asarray(target_pixels, dtype=np.float64).ravel()
#    r = np.asarray(ref_pixels, dtype=np.float64).ravel()
#    if t.size == 0 or r.size == 0:
#        return 0.0
#    sd = float(r.std())
#    if sd < _EPS:
#        return 0.0
#    return (float(t.mean()) - float(r.mean())) / sd
#
#
## ---------------------------------------------------------------------------
## ROI SNR (adapted from ebeam_snr.calculate_roi_snr)
## ---------------------------------------------------------------------------
#
#@dataclass
#class RoiSnrResult:
#    """SNR and supporting statistics for one defect ROI.
#
#    Attributes
#    ----------
#    snr_signed      : (mu_defect - mu_background) / sigma_background, signed
#                      (canonical e-beam definition; negative for dark defects).
#    snr_abs         : |snr_signed| clipped to [0, 1e6] (legacy 'snr' value).
#    defect_mean/std : Statistics inside the defect rect.
#    background_mean/std : Statistics of the surrounding background ring.
#    contrast        : |defect_mean - background_mean|.
#    contrast_ratio  : defect_mean / background_mean.
#    edge_sharpness  : Mean Sobel gradient magnitude inside the defect rect.
#    dvi             : Defect Visibility Index = snr_abs * sqrt(|contrast_ratio|).
#    """
#    snr_signed: float
#    snr_abs: float
#    defect_mean: float
#    defect_std: float
#    background_mean: float
#    background_std: float
#    contrast: float
#    contrast_ratio: float
#    edge_sharpness: float
#    dvi: float
#
#
#def roi_snr(
#    image: np.ndarray,
#    rect_px: Tuple[int, int, int, int],
#    background_margin: int = 20
#) -> Optional[RoiSnrResult]:
#    """Calculate SNR for a defect ROI.
#
#    SNR = (mu_defect - mu_background) / sigma_background
#
#    Args:
#        image: Grayscale image as numpy array.
#        rect_px: Defect region of interest as a pixel-space (x, y, w, h) tuple.
#        background_margin: Pixels to expand around ROI for background estimation.
#
#    Returns:
#        RoiSnrResult with SNR and related statistics, or None if failed.
#    """
#    if image is None:
#        return None
#
#    h, w = image.shape[:2]
#    rx, ry, rw, rh = rect_px
#
#    # Validate ROI bounds
#    x1, y1 = max(0, int(rx)), max(0, int(ry))
#    x2, y2 = min(w, int(rx) + int(rw)), min(h, int(ry) + int(rh))
#
#    if x2 <= x1 or y2 <= y1:
#        return None
#
#    # Extract defect region
#    defect_region = image[y1:y2, x1:x2].astype(np.float32)
#
#    if defect_region.size == 0:
#        return None
#
#    # Calculate defect statistics with numerical overflow protection
#    defect_mean = float(np.clip(np.mean(defect_region), -1e6, 1e6))
#    defect_std = float(np.clip(np.std(defect_region), 0, 1e6))
#
#    # Define background region (expanded area around ROI, excluding ROI itself)
#    bg_x1 = max(0, x1 - background_margin)
#    bg_y1 = max(0, y1 - background_margin)
#    bg_x2 = min(w, x2 + background_margin)
#    bg_y2 = min(h, y2 + background_margin)
#
#    # Create mask for background (expanded region minus defect region)
#    bg_mask = np.zeros((bg_y2 - bg_y1, bg_x2 - bg_x1), dtype=bool)
#    bg_mask[:, :] = True
#
#    # Mask out the defect region
#    inner_x1 = x1 - bg_x1
#    inner_y1 = y1 - bg_y1
#    inner_x2 = x2 - bg_x1
#    inner_y2 = y2 - bg_y1
#    bg_mask[inner_y1:inner_y2, inner_x1:inner_x2] = False
#
#    background_region = image[bg_y1:bg_y2, bg_x1:bg_x2].astype(np.float32)
#    background_values = background_region[bg_mask]
#
#    if background_values.size < 10:
#        # Not enough background pixels, use whole expanded region
#        background_values = background_region.flatten()
#
#    # Calculate background statistics with numerical overflow protection
#    background_mean = float(np.clip(np.mean(background_values), -1e6, 1e6))
#    background_std = float(np.clip(np.std(background_values), 0, 1e6))
#
#    # Signed SNR via the canonical primitive; absolute SNR keeps the original
#    # clipped formula for backward compatibility.
#    snr_signed_val = float(np.clip(snr_signed(defect_region, background_values), -1e6, 1e6))
#    if background_std < 1e-8 or not np.isfinite(background_std):
#        snr_abs = 0.0
#    else:
#        contrast_value = abs(defect_mean - background_mean)
#        snr_abs = float(np.clip(contrast_value / background_std, 0, 1e6))
#
#    # Calculate Contrast Ratio with numerical stability
#    if abs(background_mean) > 1e-8 and np.isfinite(background_mean):
#        contrast_ratio = float(np.clip(defect_mean / background_mean, -1e6, 1e6))
#    else:
#        contrast_ratio = 0.0
#
#    # Calculate Edge Sharpness (using Sobel gradient magnitude at ROI boundary)
#    try:
#        # Get the defect patch for edge analysis
#        defect_patch = image[y1:y2, x1:x2]
#        if defect_patch.size > 0 and defect_patch.shape[0] >= 3 and defect_patch.shape[1] >= 3:
#            sobel_x = cv2.Sobel(defect_patch, cv2.CV_64F, 1, 0, ksize=3)
#            sobel_y = cv2.Sobel(defect_patch, cv2.CV_64F, 0, 1, ksize=3)
#            gradient_mag = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
#            edge_sharpness = float(np.clip(np.mean(gradient_mag), 0, 1e6))
#        else:
#            edge_sharpness = 0.0
#    except Exception:
#        edge_sharpness = 0.0
#
#    # Calculate DVI (Defect Visibility Index) with numerical protection
#    try:
#        if contrast_ratio > 0 and np.isfinite(contrast_ratio):
#            sqrt_contrast = np.sqrt(abs(contrast_ratio))
#            dvi = float(np.clip(snr_abs * sqrt_contrast, 0, 1e6))
#        else:
#            dvi = float(np.clip(snr_abs, 0, 1e6))
#    except (ValueError, OverflowError):
#        dvi = float(np.clip(snr_abs, 0, 1e6))
#
#    # Final validation of all return values
#    contrast = float(np.clip(abs(defect_mean - background_mean), 0, 1e6))
#
#    return RoiSnrResult(
#        snr_signed=snr_signed_val,
#        snr_abs=snr_abs,
#        defect_mean=defect_mean,
#        defect_std=defect_std,
#        background_mean=background_mean,
#        background_std=background_std,
#        contrast=contrast,
#        contrast_ratio=contrast_ratio,
#        edge_sharpness=edge_sharpness,
#        dvi=dvi,
#    )
#
#
## ---------------------------------------------------------------------------
## Local SNR map (adapted from perspective_combine.compute_snr_map)
## ---------------------------------------------------------------------------
#
#@dataclass
#class SnrMapResult:
#    """Local SNR map result.
#
#    Attributes
#    ----------
#    map_float : float32 map normalized to [0, 1] (clip-sigma capped, then
#                scaled by the clip_percentile value); same values the legacy
#                uint8 map encoded, without the *255 quantization.
#    snr_max   : Raw (pre-clip, pre-normalization) SNR maximum in sigma units.
#    """
#    map_float: np.ndarray
#    snr_max: float
#
#    def to_uint8(self) -> np.ndarray:
#        """Return the legacy 0-255 uint8 rendering of the map."""
#        return (np.clip(self.map_float, 0.0, 1.0) * 255).astype(np.uint8)
#
#
#def compute_snr_map(
#    diff_image: np.ndarray,
#    window_size: int = 31,
#    clip_sigma: float = 3.0,
#    clip_percentile: float = 99.5,
#    exclude_border: int = 16
#) -> SnrMapResult:
#    """Compute local SNR map highlighting areas with strong signal.
#
#    Parameters
#    ----------
#    exclude_border : int
#        Pixels within this margin are zeroed before peak detection.
#        cv2.filter2D uses BORDER_REFLECT_101 by default, which causes
#        artificially low variance (and therefore inflated SNR) near
#        image edges. Setting this to >= window_size avoids false peaks.
#    """
#    if diff_image is None or diff_image.size == 0:
#        return SnrMapResult(np.zeros((100, 100), dtype=np.float32), 0.0)
#
#    img_f = diff_image.astype(np.float32)
#    if img_f.max() > 1.5:
#        img_f = img_f / 255.0
#
#    if window_size % 2 == 0:
#        window_size += 1
#
#    kernel = np.ones((window_size, window_size), np.float32) / (window_size * window_size)
#
#    local_mean = cv2.filter2D(img_f, -1, kernel)
#    local_sq_mean = cv2.filter2D(img_f ** 2, -1, kernel)
#    local_var = local_sq_mean - local_mean ** 2
#    local_var = np.maximum(local_var, 1e-6)
#    local_std = np.sqrt(local_var)
#
#    global_mean = np.mean(img_f)
#    snr = np.abs(local_mean - global_mean) / (local_std + 1e-6)
#
#    # Zero out border region to suppress edge artifacts from reflected padding
#    if exclude_border > 0:
#        h, w = snr.shape
#        snr[:exclude_border, :] = 0
#        snr[h - exclude_border:, :] = 0
#        snr[:, :exclude_border] = 0
#        snr[:, w - exclude_border:] = 0
#
#    snr_clipped = np.clip(snr, 0, clip_sigma)
#    if clip_percentile is not None:
#        scale = float(np.percentile(snr_clipped, clip_percentile))
#    else:
#        scale = float(clip_sigma)
#    if scale < 1e-6:
#        scale = float(clip_sigma)
#
#    # Capture raw SNR max before normalization
#    raw_snr_max = float(snr.max())
#
#    snr_normalized = np.clip(snr_clipped / scale, 0, 1).astype(np.float32)
#
#    return SnrMapResult(map_float=snr_normalized, snr_max=raw_snr_max)
#
#
## ---------------------------------------------------------------------------
## Center ROI Gaussian mask
## ---------------------------------------------------------------------------
#
#def center_gaussian_mask(shape: Tuple[int, int], sigma_ratio: float = 0.35) -> np.ndarray:
#    """Return a Gaussian weight mask centered on the image.
#
#    Parameters
#    ----------
#    shape : (H, W)
#    sigma_ratio : fraction of min(H, W) used as Gaussian sigma (default 0.35)
#
#    Returns
#    -------
#    float32 array in [0, 1], peak = 1.0 at image center.
#    """
#    H, W = shape
#    cy, cx = H / 2.0, W / 2.0
#    sigma = min(H, W) * sigma_ratio
#    Y, X = np.ogrid[:H, :W]
#    mask = np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2.0 * sigma ** 2))
#    return mask.astype(np.float32)
#
#F 8b94241c23e7cfc64aab9abda16736e476cb08a5 86 adept/core/algo/stats.py
## Vendored into ADEPT on 2026-07-27.
## Source project: PEAR — pear/core/analysis.py
##   (group_outliers, cohens_d, attribute_separability)
## Adaptations:
##   - Split the statistics helpers out of PEAR's analysis module; ROI and
##     roi_metric are imported from the sibling vendored module
##     `adept.core.algo.glv` instead of pear.core.attributes.
##   - No algorithmic changes.
#"""组间/组内统计 — outlier detection and group separability, vendored from PEAR.
#
#* ``group_outliers``          — Tukey IQR outliers within each ROI group.
#* ``cohens_d``                — standardized mean difference of two samples.
#* ``attribute_separability``  — η² (eta squared), fraction of a metric's
#  variance explained by group membership.
#"""
#
#from __future__ import annotations
#
#from typing import Dict, List, Optional
#
#import numpy as np
#
#from adept.core.algo.glv import ROI, roi_metric
#
#
#def group_outliers(image: np.ndarray, rois: List[ROI], mid: str,
#                   k: float = 1.5) -> set:
#    """rids that are Tukey outliers of ``mid`` *within their own group*.
#
#    A value outside ``[Q1 − k·IQR, Q3 + k·IQR]`` is an outlier. Groups with
#    fewer than 4 ROIs (too few for a stable IQR) are skipped.
#    """
#    out: set = set()
#    by_gid: Dict[str, List[ROI]] = {}
#    for r in rois:
#        by_gid.setdefault(r.gid, []).append(r)
#    for grs in by_gid.values():
#        if len(grs) < 4:
#            continue
#        vals = np.array([roi_metric(image, r, mid) for r in grs],
#                        dtype=np.float64)
#        q1, q3 = float(np.percentile(vals, 25)), float(np.percentile(vals, 75))
#        iqr = q3 - q1
#        if iqr <= 1e-12:
#            continue
#        lo, hi = q1 - k * iqr, q3 + k * iqr
#        for r, v in zip(grs, vals):
#            if v < lo or v > hi:
#                out.add(r.rid)
#    return out
#
#
#def cohens_d(a, b) -> Optional[float]:
#    """Standardized mean difference (a − b) / pooled_sd. None if degenerate."""
#    a = np.asarray(a, dtype=np.float64)
#    a = a[np.isfinite(a)]
#    b = np.asarray(b, dtype=np.float64)
#    b = b[np.isfinite(b)]
#    if a.size < 2 or b.size < 2:
#        return None
#    na, nb = a.size, b.size
#    sp2 = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
#    sp = float(np.sqrt(sp2))
#    if sp < 1e-12:
#        return None
#    return float((a.mean() - b.mean()) / sp)
#
#
#def attribute_separability(groups_vals) -> Optional[float]:
#    """η² (variance of a metric explained by group) in [0, 1]; higher = better
#    separation between groups. Needs 2+ non-empty groups with spread."""
#    arrs = [np.asarray(v, dtype=np.float64) for v in groups_vals]
#    arrs = [a[np.isfinite(a)] for a in arrs]
#    arrs = [a for a in arrs if a.size]
#    if len(arrs) < 2:
#        return None
#    allv = np.concatenate(arrs)
#    if allv.size < 2:
#        return None
#    grand = float(allv.mean())
#    ss_total = float(((allv - grand) ** 2).sum())
#    if ss_total < 1e-12:
#        return 0.0
#    ss_between = float(sum(a.size * (float(a.mean()) - grand) ** 2 for a in arrs))
#    return max(0.0, min(1.0, ss_between / ss_total))
#
#F 04dc4d589bd054b14d86e30bb3a8e8d894128755 641 adept/core/algo/subpixel.py
## Vendored into ADEPT on 2026-07-27.
## Source project: MMH — src/core/recipes/cmg_recipe.py (generic sub-pixel
##   edge-refinement machinery ONLY; the CMG recipe/pipeline classes were
##   NOT vendored).
## Vendored functions (public names, leading underscore dropped):
##   gaussian_filter1d, gaussian_filter1d_2d, smooth_strip_2d, extract_strip,
##   refine_yedge_threshold_crossing_batch, refine_yedge_subpixel_batch,
##   refine_yedge_threshold_crossing, refine_yedge_subpixel,
##   SubpixelResult, compute_sample_xs, aggregate_values
## Adaptations:
##   - Renamed _SubpixelResult -> SubpixelResult and made every extracted
##     helper public (underscore prefixes dropped).
##   - Also vendored the scalar refine_yedge_subpixel /
##     refine_yedge_threshold_crossing (they define the SubpixelResult
##     contract incl. fallback_reason; the batch versions mirror them).
##   - ADDED thin X-edge wrappers (refine_xedge_*) that transpose the
##     input, delegate to the Y-edge implementations, and return results
##     in original-image coordinates. New code, not in MMH.
##   - Y-edge algorithm semantics kept byte-for-byte (incl. the batch
##     versions' np.diff-based gradient and cumsum smoothing, which differ
##     from the scalar np.gradient/np.convolve versions by a small
##     systematic offset — intentional, behavior preserved).
##   - ZERO Qt; pure NumPy/OpenCV.
#"""Sub-pixel edge refinement (亚像素边缘精修), vendored from MMH's CMG recipe.
#
#Axis convention
#---------------
#A **Y-edge** is a *horizontal* boundary: intensity varies along the Y
#(row) axis. The ``refine_yedge_*`` functions take column positions
#(``sample_xs`` / ``x_center``) and a row guess ``y_guess``, and return
#refined sub-pixel **row** coordinates.
#
#An **X-edge** is a *vertical* boundary: intensity varies along the X
#(column) axis. The ``refine_xedge_*`` wrappers take row positions
#(``sample_ys`` / ``y_center``) and a column guess ``x_guess``, transpose
#the image, delegate to the Y-edge implementation, and return refined
#sub-pixel **column** coordinates in the original image frame (a
#transpose maps X-edges onto Y-edges, so coordinates come back directly;
#no further transformation is required).
#
#Two refinement methods are provided:
#
#* *gradient sub-pixel* (``refine_*_subpixel*``): dominant |gradient|
#  peak with quality gates + quadratic interpolation;
#* *threshold crossing* (``refine_*_threshold_crossing*``): linear
#  interpolation of the crossing of ``I_min + range * threshold_frac``
#  (industry standard: 50 % of local contrast).
#"""
#
#from __future__ import annotations
#
#from typing import List, NamedTuple, Optional, Union
#
#import cv2
#import numpy as np
#
#
#class SubpixelResult(NamedTuple):
#    """Return value from refine_yedge_subpixel() / refine_yedge_threshold_crossing().
#
#    fallback_reason is "" on success; one of the reason codes below on failure:
#      "invalid_image"      – image is None or wrong ndim
#      "small_window"       – search window < 3 rows
#      "flat_profile"       – profile contrast < 1 DN
#      "weak_gradient"      – peak gradient below relative threshold
#      "ambiguous_peak"     – two comparable peaks detected
#      "no_crossing"        – threshold not crossed anywhere in window (TC only)
#      "proximity_violation"– refined position too far from y_guess
#    """
#    y_refined: float
#    fallback_reason: str
#    peak_strength: float       # peak_val / p_range  (0 on fallback)
#    second_peak_ratio: float   # second_val / peak_val  (0 on fallback)
#    shift_px: float            # y_refined - y_guess  (0 on fallback)
#
#
## --------------------------------------------------------------------------- #
## filtering / strip helpers
## --------------------------------------------------------------------------- #
#def gaussian_filter1d(profile: np.ndarray, sigma: float) -> np.ndarray:
#    """Apply a 1-D Gaussian LPF using numpy convolution (no scipy dependency)."""
#    k = max(3, int(6 * sigma) | 1)          # odd kernel, at least 3 wide
#    x = np.arange(k, dtype=np.float64) - k // 2
#    kernel = np.exp(-0.5 * (x / sigma) ** 2)
#    kernel /= kernel.sum()
#    return np.convolve(profile, kernel, mode='same')
#
#
#def gaussian_filter1d_2d(arr: np.ndarray, sigma: float) -> np.ndarray:
#    """Apply per-column Gaussian LPF on a 2-D array (axis=0), pure numpy."""
#    k = max(3, int(6 * sigma) | 1)
#    x = np.arange(k, dtype=np.float64) - k // 2
#    kernel = np.exp(-0.5 * (x / sigma) ** 2)
#    kernel /= kernel.sum()
#    result = np.zeros_like(arr, dtype=np.float64)
#    for col in range(arr.shape[1]):
#        result[:, col] = np.convolve(arr[:, col], kernel, mode='same')
#    return result
#
#
#def smooth_strip_2d(strip: np.ndarray, k: int) -> np.ndarray:
#    """Per-column moving average on a 2-D strip, pure numpy.
#
#    k is forced to the nearest odd integer ≥ 3 internally.
#    Returns shape (n_rows - 1, n_cols) for any k > 1 after forcing, or
#    (n_rows, n_cols) unchanged when k ≤ 1.  The one-row loss is intentional:
#    edge crossings always occur well inside the search window.
#    """
#    if k <= 1:
#        return strip
#    k = k | 1
#    pad = np.pad(strip, ((k // 2, k // 2), (0, 0)), mode='edge')
#    cs = np.cumsum(pad, axis=0, dtype=np.float64)
#    return (cs[k:] - cs[:-k]) / k
#
#
#def extract_strip(
#    image: np.ndarray,
#    sample_xs: list,
#    y_guess: float,
#    search_half: int,
#    smooth_k: int,
#    profile_lpf_sigma: float,
#) -> tuple:
#    """Extract, LPF-filter, and smooth a 2-D strip for all valid sample_xs.
#
#    Returns (strip, y_lo, valid_mask) where
#      strip      – shape (window_height, n_valid_cols), dtype float64
#      y_lo       – int, top row of the search window
#      valid_mask – list[bool], True where sample_xs[i] is inside the image
#    """
#    h, w = image.shape[:2]
#    y_lo = max(0, int(round(y_guess)) - search_half)
#    y_hi = min(h, int(round(y_guess)) + search_half + 1)
#
#    valid_mask = [0 <= x < w for x in sample_xs]
#    valid_xs = [x for x, ok in zip(sample_xs, valid_mask) if ok]
#
#    strip = image[y_lo:y_hi, valid_xs].astype(np.float64)
#
#    if profile_lpf_sigma > 0.0:
#        strip = gaussian_filter1d_2d(strip, profile_lpf_sigma)
#
#    strip = smooth_strip_2d(strip, smooth_k)
#
#    return strip, y_lo, valid_mask
#
#
## --------------------------------------------------------------------------- #
## batch Y-edge refinement
## --------------------------------------------------------------------------- #
#def refine_yedge_threshold_crossing_batch(
#    image: np.ndarray,
#    sample_xs: list,
#    y_guess: float,
#    search_half: int = 10,
#    proximity: int = 8,
#    smooth_k: int = 3,
#    threshold_frac: float = 0.5,
#    profile_lpf_sigma: float = 0.0,
#) -> list:
#    """Vectorised TC refinement: one 2-D strip extraction for all sample_xs.
#
#    Returns list[float | None] of length len(sample_xs).
#    """
#    if not sample_xs or image is None or image.ndim < 2:
#        return [None] * len(sample_xs)
#
#    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#    h = img.shape[0]
#    y_lo_check = max(0, int(round(y_guess)) - search_half)
#    y_hi_check = min(h, int(round(y_guess)) + search_half + 1)
#    if y_hi_check - y_lo_check < 3:
#        return [None] * len(sample_xs)
#
#    strip, y_lo, valid_mask = extract_strip(
#        img, sample_xs, y_guess, search_half, smooth_k, profile_lpf_sigma
#    )
#    if strip.shape[0] < 2 or strip.shape[1] == 0:
#        return [None] * len(sample_xs)
#
#    col_min = strip.min(axis=0)
#    col_max = strip.max(axis=0)
#    col_range = col_max - col_min
#    threshold = col_min + col_range * threshold_frac
#
#    centered = strip - threshold[np.newaxis, :]
#    signs = np.sign(centered)
#    cross_mask = (signs[:-1] * signs[1:]) <= 0   # shape (n-1, n_cols)
#
#    results_valid: list = []
#    for col_idx in range(strip.shape[1]):
#        if col_range[col_idx] < 1.0:
#            results_valid.append(None)
#            continue
#        cross_rows = np.where(cross_mask[:, col_idx])[0]
#        if len(cross_rows) == 0:
#            results_valid.append(None)
#            continue
#        best_crossing = None
#        best_dist = float('inf')
#        thr = threshold[col_idx]
#        for i in cross_rows:
#            a_val = strip[i, col_idx]
#            b_val = strip[i + 1, col_idx]
#            denom = b_val - a_val
#            frac = (thr - a_val) / denom if abs(denom) > 1e-12 else 0.5
#            crossing = float(y_lo) + i + max(0.0, min(1.0, frac))
#            dist = abs(crossing - y_guess)
#            if dist < best_dist:
#                best_dist = dist
#                best_crossing = crossing
#        if best_crossing is None or abs(best_crossing - y_guess) > proximity:
#            results_valid.append(None)
#        else:
#            results_valid.append(best_crossing)
#
#    results: list = []
#    valid_iter = iter(results_valid)
#    for ok in valid_mask:
#        results.append(next(valid_iter) if ok else None)
#    return results
#
#
#def refine_yedge_subpixel_batch(
#    image: np.ndarray,
#    sample_xs: list,
#    y_guess: float,
#    search_half: int = 10,
#    proximity: int = 5,
#    smooth_k: int = 5,
#    min_grad_frac: float = 0.10,
#    peak_ratio_thr: float = 0.60,
#    profile_lpf_sigma: float = 0.0,
#) -> list:
#    """Vectorised Gradient refinement: one 2-D strip extraction for all sample_xs.
#
#    Mirrors the scalar refine_yedge_subpixel logic (gradient peak + quadratic
#    interpolation + peak dominance check) but extracts one 2-D strip and
#    computes the abs-gradient array across all columns simultaneously.
#
#    Returns list[float | None] of length len(sample_xs).
#    """
#    if not sample_xs or image is None or image.ndim < 2:
#        return [None] * len(sample_xs)
#
#    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#    h = img.shape[0]
#    y_lo_check = max(0, int(round(y_guess)) - search_half)
#    y_hi_check = min(h, int(round(y_guess)) + search_half + 1)
#    n = y_hi_check - y_lo_check
#    if n < 3:
#        return [None] * len(sample_xs)
#
#    strip, y_lo, valid_mask = extract_strip(
#        img, sample_xs, y_guess, search_half, smooth_k, profile_lpf_sigma
#    )
#    if strip.shape[0] < 2 or strip.shape[1] == 0:
#        return [None] * len(sample_xs)
#
#    n_s = strip.shape[0]   # may be n-1 after smoothing
#    col_min = strip.min(axis=0)
#    col_max = strip.max(axis=0)
#    col_range = col_max - col_min   # shape (n_cols,)
#
#    # Vectorised absolute gradient: shape (n_s-1, n_cols)
#    abs_grad = np.abs(np.diff(strip, axis=0))
#
#    # Search margins (match scalar version: margin = k//2 + 1)
#    k = smooth_k | 1
#    margin = max(1, k // 2 + 1)
#    lo_m = margin
#    hi_m = max(lo_m + 1, n_s - margin)
#
#    results_valid: list = []
#    for col_idx in range(strip.shape[1]):
#        p_range = col_range[col_idx]
#        if p_range < 1.0:
#            results_valid.append(None)
#            continue
#
#        min_grad_abs = min_grad_frac * p_range
#        search_slice = abs_grad[lo_m:hi_m, col_idx]
#        if len(search_slice) < 1:
#            results_valid.append(None)
#            continue
#
#        peak_in_slice = int(np.argmax(search_slice))
#        peak_val = float(search_slice[peak_in_slice])
#        peak_local = peak_in_slice + lo_m
#
#        if peak_val < min_grad_abs:
#            results_valid.append(None)
#            continue
#
#        # Peak dominance check (exclusion zone matches scalar)
#        _excl_r = k // 2 + 2
#        _excl_l = k // 2 + 1
#        mask = np.ones(len(search_slice), dtype=bool)
#        excl_lo = max(0, peak_in_slice - _excl_l)
#        excl_hi = min(len(search_slice), peak_in_slice + _excl_r)
#        mask[excl_lo:excl_hi] = False
#        second_val = float(search_slice[mask].max()) if mask.any() else 0.0
#        if mask.any() and second_val > peak_ratio_thr * peak_val:
#            results_valid.append(None)   # ambiguous_peak
#            continue
#
#        # Quadratic subpixel interpolation on gradient peak
#        col_grad = abs_grad[:, col_idx]
#        if 0 < peak_local < n_s - 2:
#            a = col_grad[peak_local - 1]
#            b = col_grad[peak_local]
#            c = col_grad[peak_local + 1]
#            denom = a - 2.0 * b + c
#            delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
#            peak_sub = float(peak_local) + delta
#        else:
#            peak_sub = float(peak_local)
#
#        peak_sub = max(0.0, min(float(n_s - 1), peak_sub))
#        refined = float(y_lo) + peak_sub
#
#        if abs(refined - y_guess) > proximity:
#            results_valid.append(None)
#            continue
#
#        results_valid.append(refined)
#
#    results: list = []
#    valid_iter = iter(results_valid)
#    for ok in valid_mask:
#        results.append(next(valid_iter) if ok else None)
#    return results
#
#
## --------------------------------------------------------------------------- #
## scalar Y-edge refinement (SubpixelResult contract)
## --------------------------------------------------------------------------- #
#def refine_yedge_subpixel(
#    image: np.ndarray,
#    x_center: float,
#    y_guess: float,
#    half_col: int = 3,
#    search_half: int = 10,
#    proximity: int = 5,
#    smooth_k: int = 5,
#    min_grad_frac: float = 0.10,
#    peak_ratio_thr: float = 0.60,
#    profile_lpf_sigma: float = 0.0,
#) -> SubpixelResult:
#    """Refine a Y-edge position to subpixel precision using gradient-based detection.
#
#    Extracts a narrow column profile from the raw grayscale image around
#    (x_center, y_guess), finds the dominant gradient peak with quality checks,
#    and applies quadratic subpixel interpolation.
#
#    Constraints enforced:
#    - Relative gradient threshold (min_grad_frac × profile contrast range)
#    - Peak dominance: rejects profiles with multiple comparable peaks
#    - Proximity: refined result must lie within ±proximity px of y_guess
#    - Search window strictly bounded to ±search_half px of y_guess
#
#    Returns SubpixelResult with fallback_reason="" on success, or a reason
#    code string on failure (y_refined == y_guess in that case).
#    """
#    _fallback = lambda reason: SubpixelResult(y_guess, reason, 0.0, 0.0, 0.0)
#
#    if image is None or image.ndim < 2:
#        return _fallback("invalid_image")
#
#    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#    h, w = img.shape
#
#    # Step 1: narrow column strip around x_center
#    x0 = max(0, int(x_center) - half_col)
#    x1 = min(w, int(x_center) + half_col + 1)
#    if x1 - x0 < 1:
#        return _fallback("invalid_image")
#
#    # Step 2: Y search window strictly bounded to ±search_half px
#    y_lo = max(0, int(round(y_guess)) - search_half)
#    y_hi = min(h, int(round(y_guess)) + search_half + 1)
#    n = y_hi - y_lo
#    if n < 3:
#        return _fallback("small_window")
#
#    # Step 3: 1D profile — mean intensity over X strip
#    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)
#
#    # Step 3b: optional Gaussian LPF pre-filter (applied before moving-average)
#    if profile_lpf_sigma > 0.0:
#        profile = gaussian_filter1d(profile, profile_lpf_sigma)
#
#    # Step 4: relative gradient threshold — profile must have visible contrast
#    p_range = float(profile.max() - profile.min())
#    if p_range < 1.0:           # essentially flat region → no edge to find
#        return _fallback("flat_profile")
#    min_grad_abs = min_grad_frac * p_range
#
#    # Step 5: moving-average smoothing
#    k = smooth_k | 1            # ensure odd kernel
#    if n >= k:
#        kernel = np.ones(k, dtype=np.float64) / k
#        profile = np.convolve(profile, kernel, mode='same')
#
#    # Step 6: absolute gradient
#    abs_grad = np.abs(np.gradient(profile))
#
#    # Step 7: search interior only (avoid convolution boundary artefacts).
#    # Margin must be k//2+1 so that abs_grad values that depend on zero-padded
#    # smoothed samples are excluded (np.convolve 'same' contaminates k//2 samples
#    # on each side, and np.gradient then propagates one more index outward).
#    margin = max(1, k // 2 + 1)
#    lo_m = margin
#    hi_m = min(max(lo_m + 1, n - margin), n)
#    search_slice = abs_grad[lo_m:hi_m]
#    if len(search_slice) < 1:
#        return _fallback("small_window")
#
#    peak_in_slice = int(np.argmax(search_slice))
#    peak_local = peak_in_slice + lo_m
#    peak_val = abs_grad[peak_local]
#
#    # Step 8: relative gradient threshold check
#    if peak_val < min_grad_abs:
#        return _fallback("weak_gradient")
#
#    # Step 9: peak dominance check.
#    # A smoothed step edge creates a gradient plateau of width ≈ k-1 samples, so
#    # the exclusion zone must be wide enough to cover it: ±(k//2+1) from the peak.
#    _excl_r = k // 2 + 2   # half-width on the right (exclusive upper bound offset)
#    _excl_l = k // 2 + 1   # half-width on the left
#    mask = np.ones(len(search_slice), dtype=bool)
#    excl_lo = max(0, peak_in_slice - _excl_l)
#    excl_hi = min(len(search_slice), peak_in_slice + _excl_r)
#    mask[excl_lo:excl_hi] = False
#    second_val = float(search_slice[mask].max()) if mask.any() else 0.0
#    if mask.any() and second_val > peak_ratio_thr * peak_val:
#        return _fallback("ambiguous_peak")  # multiple peaks of similar height
#
#    # Step 10: quadratic subpixel interpolation on gradient peak
#    if 0 < peak_local < n - 1:
#        a = abs_grad[peak_local - 1]
#        b = abs_grad[peak_local]
#        c = abs_grad[peak_local + 1]
#        denom = a - 2.0 * b + c
#        delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
#        peak_sub = float(peak_local) + delta
#    else:
#        peak_sub = float(peak_local)
#
#    # Clamp to search window
#    peak_sub = max(0.0, min(float(n - 1), peak_sub))
#    refined = float(y_lo) + peak_sub
#
#    # Step 11: proximity constraint — refined must stay close to initial guess
#    if abs(refined - y_guess) > proximity:
#        return _fallback("proximity_violation")
#
#    peak_strength = peak_val / (p_range + 1e-12)
#    ratio = second_val / peak_val if peak_val > 0 else 0.0
#    return SubpixelResult(refined, "", peak_strength, ratio, refined - y_guess)
#
#
#def refine_yedge_threshold_crossing(
#    image: np.ndarray,
#    x_center: float,
#    y_guess: float,
#    half_col: int = 3,
#    search_half: int = 10,
#    proximity: int = 8,
#    smooth_k: int = 3,
#    threshold_frac: float = 0.5,
#    profile_lpf_sigma: float = 0.0,
#) -> SubpixelResult:
#    """Refine a Y-edge by finding where intensity crosses a threshold level.
#
#    threshold = I_min + (I_max - I_min) * threshold_frac
#
#    I_max and I_min are the extrema of the smoothed 1D profile within the
#    search window.  The crossing closest to y_guess is returned.  Industry
#    standard uses threshold_frac=0.5 (50 % of the local contrast range).
#
#    Fallback reasons (y_refined == y_guess on failure):
#      "invalid_image"      – image None or wrong ndim
#      "small_window"       – search window < 3 rows
#      "flat_profile"       – profile contrast < 1 DN
#      "no_crossing"        – threshold not crossed anywhere in window
#      "proximity_violation"– closest crossing too far from y_guess
#    """
#    _fallback = lambda reason: SubpixelResult(y_guess, reason, 0.0, 0.0, 0.0)
#
#    if image is None or image.ndim < 2:
#        return _fallback("invalid_image")
#
#    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#    h, w = img.shape
#
#    # Step 1: narrow column strip
#    x0 = max(0, int(x_center) - half_col)
#    x1 = min(w, int(x_center) + half_col + 1)
#    if x1 - x0 < 1:
#        return _fallback("invalid_image")
#
#    # Step 2: Y search window
#    y_lo = max(0, int(round(y_guess)) - search_half)
#    y_hi = min(h, int(round(y_guess)) + search_half + 1)
#    n = y_hi - y_lo
#    if n < 3:
#        return _fallback("small_window")
#
#    # Step 3: 1D profile — mean intensity over X strip
#    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)
#
#    # Step 3b: optional Gaussian LPF pre-filter (applied before moving-average)
#    if profile_lpf_sigma > 0.0:
#        profile = gaussian_filter1d(profile, profile_lpf_sigma)
#
#    # Step 4: contrast check
#    p_range = float(profile.max() - profile.min())
#    if p_range < 1.0:
#        return _fallback("flat_profile")
#
#    # Step 5: moving-average smoothing
#    k = smooth_k | 1
#    if n >= k:
#        kernel = np.ones(k, dtype=np.float64) / k
#        profile = np.convolve(profile, kernel, mode='same')
#
#    # Step 6: threshold level from smoothed profile extrema
#    i_max = float(profile.max())
#    i_min = float(profile.min())
#    threshold = i_min + (i_max - i_min) * threshold_frac
#
#    # Step 7: find all crossings, keep the one closest to y_guess
#    best_crossing: Optional[float] = None
#    best_dist = float('inf')
#    for i in range(n - 1):
#        a, b_val = profile[i], profile[i + 1]
#        # Crossed when the two samples straddle the threshold (or one equals it)
#        if (a - threshold) * (b_val - threshold) <= 0:
#            denom = b_val - a
#            t = (threshold - a) / denom if abs(denom) > 1e-12 else 0.5
#            t = max(0.0, min(1.0, t))
#            crossing = float(y_lo) + i + t
#            dist = abs(crossing - y_guess)
#            if dist < best_dist:
#                best_dist = dist
#                best_crossing = crossing
#
#    if best_crossing is None:
#        return _fallback("no_crossing")
#
#    # Step 8: proximity constraint
#    if abs(best_crossing - y_guess) > proximity:
#        return _fallback("proximity_violation")
#
#    contrast = (i_max - i_min) / (i_max + 1e-12)
#    return SubpixelResult(best_crossing, "", contrast, 0.0, best_crossing - y_guess)
#
#
## --------------------------------------------------------------------------- #
## sampling / aggregation helpers
## --------------------------------------------------------------------------- #
#def compute_sample_xs(x_start: int, x_end: int, mode) -> List[int]:
#    """Return list of x positions to sample in [x_start, x_end).
#
#    mode: "all" → every integer; int N → N evenly spaced positions.
#    """
#    xs = list(range(int(x_start), int(x_end)))
#    if not xs:
#        return xs
#    if mode == "all" or not isinstance(mode, int):
#        return xs
#    N = max(1, min(int(mode), len(xs)))
#    if N >= len(xs):
#        return xs
#    indices = [int(round(i)) for i in np.linspace(0, len(xs) - 1, N)]
#    return [xs[i] for i in indices]
#
#
#def aggregate_values(vals: list, method: str) -> float:
#    """Aggregate float list using method: median/mean/min/max."""
#    if not vals:
#        return 0.0
#    m = method.lower()
#    if m == "mean":
#        return float(np.mean(vals))
#    if m == "min":
#        return float(np.min(vals))
#    if m == "max":
#        return float(np.max(vals))
#    return float(np.median(vals))  # default: median
#
#
## --------------------------------------------------------------------------- #
## X-edge wrappers (ADEPT additions — thin transpose adapters)
## --------------------------------------------------------------------------- #
#def _transpose_gray(image: np.ndarray) -> Optional[np.ndarray]:
#    """Grayscale-convert (if colour) then transpose. None passes through."""
#    if image is None or getattr(image, "ndim", 0) < 2:
#        return image
#    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#    return np.ascontiguousarray(img.T)
#
#
#def refine_xedge_subpixel(image: np.ndarray, y_center: float, x_guess: float,
#                          **kwargs) -> SubpixelResult:
#    """X-edge counterpart of :func:`refine_yedge_subpixel`.
#
#    Transposes the image and delegates; ``y_refined``/``shift_px`` in the
#    returned SubpixelResult are X (column) coordinates of the original image.
#    """
#    return refine_yedge_subpixel(_transpose_gray(image), y_center, x_guess,
#                                 **kwargs)
#
#
#def refine_xedge_threshold_crossing(image: np.ndarray, y_center: float,
#                                    x_guess: float, **kwargs) -> SubpixelResult:
#    """X-edge counterpart of :func:`refine_yedge_threshold_crossing`."""
#    return refine_yedge_threshold_crossing(_transpose_gray(image), y_center,
#                                           x_guess, **kwargs)
#
#
#def refine_xedge_subpixel_batch(image: np.ndarray, sample_ys: list,
#                                x_guess: float, **kwargs) -> list:
#    """X-edge counterpart of :func:`refine_yedge_subpixel_batch`.
#
#    ``sample_ys`` are row positions; the returned list holds refined X
#    (column) coordinates (or None) in the original image frame.
#    """
#    return refine_yedge_subpixel_batch(_transpose_gray(image), sample_ys,
#                                       x_guess, **kwargs)
#
#
#def refine_xedge_threshold_crossing_batch(image: np.ndarray, sample_ys: list,
#                                          x_guess: float, **kwargs) -> list:
#    """X-edge counterpart of :func:`refine_yedge_threshold_crossing_batch`."""
#    return refine_yedge_threshold_crossing_batch(_transpose_gray(image),
#                                                 sample_ys, x_guess, **kwargs)
#
#F 61ccab417e918d137718964b4a6fc9acead1c433 451 adept/core/algo/template.py
## ADEPT algorithm library — authored 2026-07-29 (F7-12).
#"""Golden Cell 模板定位：從大圖疊出一個週期，再把每張 patch 對回那個週期。
#
#為什麼要從大圖疊
#----------------
#patch 通常**比一個重複單元還小**，所以每張 patch 看到的只是週期裡的一小片，
#不同 defect 落在不同相位 —— 拿這些小片互相對位，其實沒有共同的東西可以對。
#
#但 patch 是從 EBI 機台吐出的**大圖**上裁下來的，而大圖裡看得到好幾個週期。
#所以順序反過來：先在大圖上量週期、疊出一個乾淨的 Golden Cell（GC），
#再把小 patch **滑進**這個比它大的模板裡找位置。這是有唯一解的問題，
#而「小片互相對位」不是。
#
#週期也因此不必請使用者填 —— 大圖上量得到。
#
#原點必須錨在看得見的地標（這條最容易被忽略）
#--------------------------------------------
#疊 GC 之前要決定「一個週期從哪裡開始」。``period.choose_origin`` 挑的是
#**讓疊出來最銳利**的相位 —— 但對一張週期性影像來說，任何相位疊出來都一樣銳利，
#所以它在數個幾乎等價的候選之間選哪一個，實務上是任意的。
#
#後果很嚴重而且很安靜：換一批資料重算 GC，相位一變，**使用者標在 GC 上的框就
#跟著平移了**，而畫面上不會有任何錯誤訊息 —— 框還在、數字還有，只是量錯地方。
#
#所以 :func:`build_golden_cell` 疊完之後會再**捲動**一次，把「最強的上升邊」
#（暗→亮的轉折）擺到第 0 欄。那是影像上認得出來的同一個物理特徵，
#換一批資料仍然指向同一個地方。用**上升**邊而不是「最強的邊」是因為一個週期裡
#通常有一對方向相反的邊，強度相近時「最強」會在兩者之間跳。
#
#比對用 NCC
#----------
#大圖與 patch 是不同時間、不同增益拍的，整體亮度不會一樣。
#``cv2.TM_CCOEFF_NORMED`` 對線性的亮度／對比變化免疫，直接比灰階差則會被
#亮度差主導。
#
#「定得出來嗎」要過三關
#----------------------
#比對一定會回一個「最像的位置」，就算那張 patch 根本沒有特徵。所以三關都要過：
#
#1. **這張 patch 上有結構嗎**（``patch_structure``）。這一關做的是最重的工，
#   而且它是唯一問對問題的一關 —— 沒有結構就是定不出來，跟門檻調得多好無關。
#2. **分數**（NCC 的最高值）。
#3. **峰有多突出**（最高分與次高分的差，摺回一個週期之後才比）。
#
#只靠 2、3 是不夠的，實測過：一張純雜訊的 32 寬 patch 收窄成曲線之後，跟模板的
#隨機相關標準差大約 ``1/√32 ≈ 0.18``，**靠運氣就拿得到 0.5 的分數**。門檻拉高
#只是把問題推遲 —— 真實資料的分數本來就比合成的低，拉高會開始殺掉真的。
#
#實測的分佈（合成資料，20 個雜訊種子）：
#有結構的 structure 38–86、margin 0.36–0.60；均勻的 structure 0.5–1.2、
#margin 0.01–0.24。**structure 這一關差了一個數量級**，另外兩關會重疊。
#"""
#from __future__ import annotations
#
#import base64
#import zlib
#from dataclasses import dataclass, field
#from typing import Any, List, Optional, Tuple
#
#import cv2
#import numpy as np
#
#from . import golden as algo_golden
#from . import period as algo_period
#
#__all__ = [
#    "GoldenCell", "MatchResult", "build_golden_cell", "anchor_cell",
#    "encode_cell", "decode_cell", "tile_cell", "match_patch", "roi_in_patch",
#    "patch_structure", "MIN_PERIOD_CONFIDENCE",
#    "CELL_ENCODING",
#]
#
##: 模板在 recipe 裡的編碼：``"gc1:<w>x<h>:<base64(zlib(raw uint8))>"``。
##:
##: 為什麼是 base64 而不是外部檔案：recipe 必須是**一個可以寄給別人的純文字檔**。
##: 存路徑的話，圖被搬走、被換掉、下個月用了另一張大圖，結果會安靜地變。
##: base64 是 ASCII，所以 repo 與 recipe 的「只有純文字」不變量仍然成立
##: （公司機的 DLP 擋的是二進位壓縮檔，見 docs/HANDOVER.md §5）。
##: 先過 zlib：SEM 的 cell 有雜訊、壓不了太多（實測約剩七成），
##: 但一個週期本來就小，這個大小塞進 recipe JSON 完全沒問題。
#CELL_ENCODING = "gc1"
#
##: 一軸上的週期信心要多少才算數（``period.estimate_period`` 的 0–100 分）。
##: 實測：純雜訊約 20，真的有週期的約 87 —— 門檻放中間兩邊都安全。
##: 呼叫端自己指定 ``px``/``py`` 時不套用（那是使用者明說的，不是猜的）。
#MIN_PERIOD_CONFIDENCE = 40.0
#
#
#@dataclass
#class GoldenCell:
#    """從大圖疊出來的一個週期，以及疊得好不好的證據。"""
#
#    cell: np.ndarray                    # (py, px) uint8
#    px: int
#    py: int
#    ghosting: float = 0.0               # 0–100，越高越銳利（疊得越準）
#    lap_var: float = 0.0                # 未飽和的原始值（要比較大小時用這個）
#    confidence_x: float = 0.0
#    confidence_y: float = 0.0
#    anchor: Tuple[int, int] = (0, 0)    # 為了錨定地標捲動了多少
#    n_cells: int = 0
#    #: 這一軸上真的量到週期了嗎。**一維的 layout 是常態**（垂直條紋只有 X 有
#    #: 週期），那時候另一軸不做定位 —— 它上面沒有東西可以定位。
#    periodic_x: bool = True
#    periodic_y: bool = True
#    warnings: List[str] = field(default_factory=list)
#
#    @property
#    def shape(self) -> Tuple[int, int]:
#        return (int(self.py), int(self.px))
#
#    @property
#    def periodic(self) -> Tuple[bool, bool]:
#        return (bool(self.periodic_x), bool(self.periodic_y))
#
#
#@dataclass
#class MatchResult:
#    """一張 patch 對回 GC 的結果。"""
#
#    phase_x: int = 0                    # patch 左上角落在 cell 的哪一格
#    phase_y: int = 0
#    score: float = 0.0                  # 最高的 NCC 分數（-1..1）
#    margin: float = 0.0                 # 最高分與鄰域外次高分的差 = 峰有多突出
#    structure: float = 0.0              # 這張 patch 自己有沒有結構（見 patch_structure）
#    ok: bool = False
#
#
#def _gray_u8(img: Any) -> np.ndarray:
#    a = np.asarray(img)
#    if a.ndim == 3:
#        a = a.mean(axis=2)
#    f = a.astype(np.float32)
#    if f.size == 0:
#        return np.zeros((0, 0), np.uint8)
#    lo, hi = float(np.nanmin(f)), float(np.nanmax(f))
#    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
#        return np.zeros(f.shape, np.uint8)
#    if lo >= -0.5 and hi <= 255.5:
#        return np.clip(f, 0, 255).astype(np.uint8)
#    return np.clip((f - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
#
#
## --------------------------------------------------------------------------- #
## 原點錨定
## --------------------------------------------------------------------------- #
#def _rising_edge_index(profile: np.ndarray) -> Optional[int]:
#    """一條週期性曲線上「最強的上升邊」在哪（找不到明確的邊回 None）。
#
#    用 ``np.gradient`` 的**最大正值**。取正值而不是絕對值，是因為一個週期裡
#    通常有一對方向相反的邊，強度相近時「最強的邊」會在兩者之間跳 ——
#    而那正是我們要避免的那種安靜的漂移。
#    """
#    p = np.asarray(profile, dtype=np.float32)
#    if p.size < 3:
#        return None
#    # 週期性訊號要用環狀梯度，否則兩端的邊會被截掉
#    grad = np.roll(p, -1) - np.roll(p, 1)
#    peak = float(grad.max())
#    if peak <= 0.0:
#        return None
#    # 上升邊要真的比一般的地方陡，否則這條曲線上沒有邊（同 algo/profile.py）
#    if peak < 1.2 * float(np.median(np.abs(grad)) or 1e-9):
#        return None
#    return int(np.argmax(grad))
#
#
#def anchor_cell(cell: np.ndarray,
#                axes: Tuple[bool, bool] = (True, True),
#                ) -> Tuple[np.ndarray, Tuple[int, int]]:
#    """把 GC 捲動到「最強的上升邊在第 0 欄／第 0 列」。回傳 ``(cell, (dx, dy))``。
#
#    捲動用 ``np.roll`` —— 對一個週期來說捲動是無損的（它本來就是環狀的）。
#
#    某一軸上沒有明確的邊時**那一軸不動**：硬要錨一個不存在的地標，
#    等於用雜訊決定相位，比不錨還糟。
#    """
#    a = np.asarray(cell)
#    if a.ndim != 2 or a.size == 0:
#        return a, (0, 0)
#    dx = _rising_edge_index(a.mean(axis=0)) if axes[0] else None
#    dy = _rising_edge_index(a.mean(axis=1)) if axes[1] else None
#    out = a
#    if dx:
#        out = np.roll(out, -int(dx), axis=1)
#    if dy:
#        out = np.roll(out, -int(dy), axis=0)
#    return out, (int(dx or 0), int(dy or 0))
#
#
## --------------------------------------------------------------------------- #
## 建模板
## --------------------------------------------------------------------------- #
#def build_golden_cell(image: Any, px: Optional[int] = None,
#                      py: Optional[int] = None, method: str = "mean",
#                      anchor: bool = True) -> GoldenCell:
#    """從大圖疊出一個 Golden Cell。
#
#    ``px`` / ``py`` 留空就從影像自己量（``period.estimate_period``）。
#    量不到週期時回一個空的 cell 並在 ``warnings`` 說明 —— 不猜。
#    """
#    gray = _gray_u8(image)
#    warnings: List[str] = []
#    if gray.size == 0:
#        return GoldenCell(cell=np.zeros((0, 0), np.uint8), px=0, py=0,
#                          warnings=["the image is empty"])
#
#    # 使用者自己指定的週期一律相信（信心檢查只針對「量出來的」那一軸）
#    given_x, given_y = px is not None, py is not None
#    conf_x = 100.0 if given_x else 0.0
#    conf_y = 100.0 if given_y else 0.0
#    if not (given_x and given_y):
#        est = algo_period.estimate_period(gray)
#        if not given_x:
#            px, conf_x = int(est.px or 0), float(est.confidence_x)
#        if not given_y:
#            py, conf_y = int(est.py or 0), float(est.confidence_y)
#        warnings.extend(list(est.warnings or []))
#
#    px, py = int(px or 0), int(py or 0)
#    h, w = gray.shape[:2]
#    # 一維的 layout 是常態：垂直條紋只有 X 有週期，Y 上量不到東西**是正確的**。
#    # 那一軸就取整張影像的長度當「一格」——反正它上面沒有相位可言。
#    #
#    # 但「量到一個數字」不等於「真的有週期」：純雜訊也會被找出一個假週期
#    # （實測 confidence 20 上下，而真的有週期的是 87）。所以信心不夠的那一軸
#    # 一律當成沒有週期 —— 拿假週期疊出來的模板會糊掉，而糊掉的模板會讓後面
#    # 每一顆都對錯。
#    periodic_x = px >= 2 and conf_x >= MIN_PERIOD_CONFIDENCE
#    periodic_y = py >= 2 and conf_y >= MIN_PERIOD_CONFIDENCE
#    if not periodic_x and not periodic_y:
#        return GoldenCell(cell=np.zeros((0, 0), np.uint8), px=px, py=py,
#                          confidence_x=conf_x, confidence_y=conf_y,
#                          periodic_x=False, periodic_y=False,
#                          warnings=warnings + [
#                              "no repeating period could be measured in this "
#                              "image; a Golden Cell needs a periodic layout"])
#    if not periodic_x:
#        px = w
#        warnings.append("no period across the image; the cell spans the full "
#                        "width and no region is located along that direction")
#    if not periodic_y:
#        py = h
#        warnings.append("no period down the image; the cell spans the full "
#                        "height and no region is located along that direction")
#
#    origin = algo_period.choose_origin(gray.shape, px, py, image=gray)
#    cell = algo_golden.stack_cells(gray, px, py, method=method, origin=origin)
#    n_cells = len(algo_golden.tile_coords(gray.shape, px, py, origin))
#
#    roll = (0, 0)
#    if anchor:
#        cell, roll = anchor_cell(cell, axes=(periodic_x, periodic_y))
#        if roll == (0, 0) and (periodic_x or periodic_y):
#            # 沒有地標可錨 -> 相位是任意的 -> 換一批資料框會平移。
#            # 這是**必須說出來**的事，不是可以吞掉的細節。
#            warnings.append(
#                "no clear landmark to anchor the cell on; the phase of this "
#                "Golden Cell is arbitrary, so a region marked on it may shift "
#                "if the cell is rebuilt from different data")
#
#    score, lap_var, _edge = algo_golden.ghosting_score(cell)
#    return GoldenCell(cell=cell, px=px, py=py, ghosting=float(score),
#                      lap_var=float(lap_var), confidence_x=conf_x,
#                      confidence_y=conf_y, anchor=roll, n_cells=int(n_cells),
#                      periodic_x=periodic_x, periodic_y=periodic_y,
#                      warnings=warnings)
#
#
## --------------------------------------------------------------------------- #
## 存進 recipe（純文字）
## --------------------------------------------------------------------------- #
#def encode_cell(cell: np.ndarray) -> str:
#    """``(h, w)`` uint8 → ``"gc1:<w>x<h>:<base64>"``（見 :data:`CELL_ENCODING`）。"""
#    a = np.asarray(cell)
#    if a.ndim != 2 or a.size == 0:
#        return ""
#    u8 = _gray_u8(a)
#    h, w = u8.shape
#    blob = base64.b64encode(zlib.compress(u8.tobytes(), 6)).decode("ascii")
#    return "%s:%dx%d:%s" % (CELL_ENCODING, w, h, blob)
#
#
#def decode_cell(text: str) -> Optional[np.ndarray]:
#    """:func:`encode_cell` 的反向；格式不對回 ``None``（絕不 raise）。"""
#    s = str(text or "").strip()
#    if not s:
#        return None
#    try:
#        tag, size, blob = s.split(":", 2)
#        if tag != CELL_ENCODING:
#            return None
#        w, h = (int(v) for v in size.split("x"))
#        raw = zlib.decompress(base64.b64decode(blob.encode("ascii")))
#        if w < 1 or h < 1 or len(raw) != w * h:
#            return None
#        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w).copy()
#    except Exception:                       # noqa: BLE001 — 壞字串一律當沒有
#        return None
#
#
## --------------------------------------------------------------------------- #
## 比對
## --------------------------------------------------------------------------- #
#def tile_cell(cell: np.ndarray, min_w: int, min_h: int) -> np.ndarray:
#    """把一個週期接成至少 ``min_w`` × ``min_h`` 的畫布。
#
#    **一定要接**：有些 patch 剛好跨在週期的接縫上，只拿一個週期當模板，
#    那些 patch 永遠比對不到。
#    """
#    a = np.asarray(cell)
#    if a.ndim != 2 or a.size == 0:
#        return a
#    h, w = a.shape
#    ny = int(np.ceil(max(1, min_h) / float(h))) + 1
#    nx = int(np.ceil(max(1, min_w) / float(w))) + 1
#    return np.tile(a, (ny, nx))
#
#
#def patch_structure(patch: Any, axis_x: bool = True) -> float:
#    """這張 patch 上有沒有東西可以定位（同 ``algo/profile.profile_confidence``）。
#
#    為什麼相關分數本身不夠
#    ----------------------
#    比對一定會回一個「最像的位置」。一張**沒有特徵**的 patch 收窄成 32 個樣本的
#    曲線之後，跟模板隨機相關的標準差大約是 ``1/√32 ≈ 0.18`` —— 也就是說
#    **純雜訊靠運氣就可以拿到 0.4 以上的分數**，實測過。門檻拉高只是把這件事
#    推遲，不是解決它：真實資料的分數本來就比合成的低，門檻拉高會開始殺掉真的。
#
#    所以先問一個相關性完全回答不了的問題：**這張 patch 上有結構嗎？** 沒有的話
#    它就是定不出來 —— 那是資訊不夠，不是門檻沒調好。這跟投影定位用的是同一個
#    量（曲線的起伏 ÷ 雜訊尺度），所以兩張卡對「哪些 patch 定得出來」的判斷一致。
#    """
#    from . import profile as algo_profile
#
#    axis = algo_profile.AXIS_X if axis_x else algo_profile.AXIS_Y
#    smoothed, raw = algo_profile.projection(patch, axis=axis, smooth=3)
#    return algo_profile.profile_confidence(smoothed, raw)
#
#
#def match_patch(cell: np.ndarray, patch: Any,
#                min_score: float = 0.3,
#                min_margin: float = 0.05,
#                min_structure: float = 5.0,
#                periodic: Tuple[bool, bool] = (True, True)) -> MatchResult:
#    """把 ``patch`` 對回 ``cell`` 的相位。
#
#    ``margin``（峰的突出程度）是判斷「這張定得出來嗎」的依據 ——
#    見模組說明。門檻兩個都要過。
#
#    **非週期的那一軸會被壓成一維再比對。** 垂直條紋的 layout 在 Y 上沒有相位
#    可言，硬要在 Y 上搜尋只會讓相關面變平、把峰的突出程度稀釋掉 ——
#    也就是把「定得出來」誤判成「定不出來」。壓成一維之後，這條路剛好就退化成
#    投影定位在做的事（``algo/profile.py``），兩個方法在這裡是一致的。
#    """
#    c = np.asarray(cell)
#    p = _gray_u8(patch)
#    if c.ndim != 2 or c.size == 0 or p.size == 0:
#        return MatchResult()
#
#    structure = patch_structure(p, axis_x=bool(periodic[0]))
#
#    if not periodic[1]:                     # Y 沒有週期 -> 只比 X
#        c = c.mean(axis=0, keepdims=True).astype(np.float32)
#        p = p.mean(axis=0, keepdims=True).astype(np.float32)
#    elif not periodic[0]:                   # X 沒有週期 -> 只比 Y
#        c = c.mean(axis=1, keepdims=True).astype(np.float32)
#        p = p.mean(axis=1, keepdims=True).astype(np.float32)
#
#    ph, pw = p.shape
#    canvas = tile_cell(c, pw + c.shape[1], ph + c.shape[0])
#    if canvas.shape[0] < ph or canvas.shape[1] < pw:
#        return MatchResult()
#
#    surface = cv2.matchTemplate(canvas.astype(np.float32),
#                                p.astype(np.float32), cv2.TM_CCOEFF_NORMED)
#    if surface.size == 0:
#        return MatchResult()
#
#    # 相關面上每隔一個週期就有一個一模一樣的峰 —— 那些**不是**「另一個答案」，
#    # 是同一個答案的複本。所以先把整個面**摺**回一個週期（同相位取最大），
#    # 問題才變成它真正該問的那一個：**在所有可能的相位裡，最好的那個比次好的
#    # 好多少？** 整張均勻的 patch 摺完之後是平的 —— 差值接近 0。
#    cy, cx = c.shape
#    folded = _fold_to_period(surface, cx, cy)
#    peak_idx = int(np.argmax(folded))
#    fy, fx = np.unravel_index(peak_idx, folded.shape)
#    best_folded = float(folded[fy, fx])
#
#    # 遮掉峰的鄰域（環狀，因為相位是環狀的）再取次高
#    rest = folded.copy()
#    rx = max(2, folded.shape[1] // 16)
#    ry = max(2, folded.shape[0] // 16)
#    for dy in range(-ry, ry + 1):
#        for dx in range(-rx, rx + 1):
#            rest[(fy + dy) % folded.shape[0], (fx + dx) % folded.shape[1]] = -1.0
#    runner = float(rest.max()) if rest.size else -1.0
#    margin = best_folded - runner
#
#    _mn, best, _mnloc, _bl = cv2.minMaxLoc(surface)
#    ok = bool(structure >= float(min_structure)
#              and best >= float(min_score)
#              and margin >= float(min_margin))
#    return MatchResult(phase_x=int(fx % cx), phase_y=int(fy % cy),
#                       score=float(best), margin=float(margin),
#                       structure=float(structure), ok=ok)
#
#
#def _fold_to_period(surface: np.ndarray, px: int, py: int) -> np.ndarray:
#    """把相關面摺回一個週期（同相位取最大值）。"""
#    s = np.asarray(surface, dtype=np.float32)
#    h, w = s.shape
#    px, py = max(1, min(int(px), w)), max(1, min(int(py), h))
#    out = np.full((py, px), -1.0, dtype=np.float32)
#    for y0 in range(0, h, py):
#        for x0 in range(0, w, px):
#            blk = s[y0:y0 + py, x0:x0 + px]
#            out[:blk.shape[0], :blk.shape[1]] = np.maximum(
#                out[:blk.shape[0], :blk.shape[1]], blk)
#    return out
#
#
#def roi_in_patch(norm_rect: Tuple[float, float, float, float],
#                 match: MatchResult, cell_shape: Tuple[int, int],
#                 patch_shape: Tuple[int, int],
#                 periodic: Tuple[bool, bool] = (True, True),
#                 ) -> Tuple[int, int, int, int]:
#    """把「標在 GC 上的框」搬到 patch 上，回傳像素矩形 ``(x, y, w, h)``。
#
#    一個週期在 patch 裡可能出現好幾次，所以取**離 patch 中心最近**的那一個
#    —— 缺陷永遠在 patch 正中央，使用者標的框指的是「缺陷所在的那個 cell」。
#    """
#    cy, cx = int(cell_shape[0]), int(cell_shape[1])
#    ph, pw = int(patch_shape[0]), int(patch_shape[1])
#    nx, ny, nw, nh = (float(v) for v in norm_rect)
#
#    def place(cell_lo: float, cell_span: float, phase: int, period: int,
#              patch_len: int) -> Tuple[int, int]:
#        span = max(1.0, cell_span * period)
#        base = cell_lo * period - float(phase)      # k = 0 的位置
#        centre = patch_len / 2.0
#        k = round((centre - span / 2.0 - base) / float(period))
#        lo = base + k * period
#        return int(round(lo)), int(round(span))
#
#    # 沒有週期的那一軸沒有相位可言 —— 框在那個方向取滿整張 patch，
#    # 硬給一個位置等於憑空捏造資訊（同 roi_profile 的 _band_rect）。
#    x, w = place(nx, nw, match.phase_x, cx, pw) if periodic[0] else (0, pw)
#    y, h = place(ny, nh, match.phase_y, cy, ph) if periodic[1] else (0, ph)
#    return (x, y, w, h)
#
#F dcec5abad8375953a68b55b4ac771958207f81bb 141 adept/core/calibration.py
## Vendored into ADEPT on 2026-07-27.
## Source project: MMH — src/core/calibration.py
## Adaptations:
##   - Storage directory changed from ~/.mmh/calibrations/ to
##     ~/.adept/calibrations/.
##   - `save()` made atomic: profile JSON is written to a `.tmp` sibling
##     first and moved into place with os.replace (MMH wrote in place,
##     risking a truncated file on crash).
##   - CalibrationProfile / CalibrationManager API kept unchanged.
#"""Calibration profile management.
#
#Profiles are persisted as JSON files in ~/.adept/calibrations/.
#"""
#from __future__ import annotations
#
#import json
#import os
#import uuid
#from dataclasses import dataclass
#from pathlib import Path
#from typing import Any, Dict, List, Optional
#
#
#CALIBRATION_DIR = Path.home() / ".adept" / "calibrations"
#
#_FALLBACK_PROFILE_ID = "default-1nm-px"
#
#
#@dataclass
#class CalibrationProfile:
#    profile_id: str
#    profile_name: str
#    nm_per_pixel: float
#    magnification: float = 0.0
#    detector_type: str = ""
#    source: str = "manual"   # "manual" | "tiff_tag" | "imported"
#    version: int = 1
#    notes: str = ""
#
#    def to_dict(self) -> Dict[str, Any]:
#        return {
#            "profile_id": self.profile_id,
#            "profile_name": self.profile_name,
#            "nm_per_pixel": float(self.nm_per_pixel),
#            "magnification": float(self.magnification),
#            "detector_type": self.detector_type,
#            "source": self.source,
#            "version": self.version,
#            "notes": self.notes,
#        }
#
#    @staticmethod
#    def from_dict(d: dict) -> "CalibrationProfile":
#        return CalibrationProfile(
#            profile_id=d["profile_id"],
#            profile_name=d.get("profile_name", d["profile_id"]),
#            nm_per_pixel=float(d.get("nm_per_pixel", 1.0)),
#            magnification=float(d.get("magnification", 0.0)),
#            detector_type=d.get("detector_type", ""),
#            source=d.get("source", "manual"),
#            version=int(d.get("version", 1)),
#            notes=d.get("notes", ""),
#        )
#
#
#_FALLBACK = CalibrationProfile(
#    profile_id=_FALLBACK_PROFILE_ID,
#    profile_name="Default (1 nm/px)",
#    nm_per_pixel=1.0,
#    source="manual",
#    notes="Built-in fallback — update with your SEM calibration value.",
#)
#
#
#class CalibrationManager:
#    """Load, save, and list CalibrationProfile objects from disk."""
#
#    def __init__(self, cal_dir: Optional[Path] = None):
#        self._dir = cal_dir or CALIBRATION_DIR
#        self._dir.mkdir(parents=True, exist_ok=True)
#        self._profiles: Dict[str, CalibrationProfile] = {}
#        self._load_all()
#
#    def _load_all(self) -> None:
#        for f in self._dir.glob("*.json"):
#            try:
#                d = json.loads(f.read_text(encoding="utf-8"))
#                p = CalibrationProfile.from_dict(d)
#                self._profiles[p.profile_id] = p
#            except Exception:
#                pass
#
#    def list_profiles(self) -> List[CalibrationProfile]:
#        return sorted(self._profiles.values(), key=lambda p: p.profile_name)
#
#    def get(self, profile_id: str) -> Optional[CalibrationProfile]:
#        return self._profiles.get(profile_id)
#
#    def get_default(self) -> CalibrationProfile:
#        if self._profiles:
#            return next(iter(self._profiles.values()))
#        return _FALLBACK
#
#    def save(self, profile: CalibrationProfile) -> None:
#        """Persist *profile* atomically (.tmp sibling + os.replace)."""
#        path = self._dir / f"{profile.profile_id}.json"
#        tmp = path.with_suffix(path.suffix + ".tmp")
#        tmp.write_text(
#            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
#            encoding="utf-8",
#        )
#        os.replace(str(tmp), str(path))
#        self._profiles[profile.profile_id] = profile
#
#    def delete(self, profile_id: str) -> bool:
#        path = self._dir / f"{profile_id}.json"
#        if path.exists():
#            path.unlink()
#            self._profiles.pop(profile_id, None)
#            return True
#        return False
#
#    def create_new(
#        self,
#        name: str,
#        nm_per_pixel: float,
#        magnification: float = 0.0,
#        detector_type: str = "",
#        notes: str = "",
#    ) -> CalibrationProfile:
#        p = CalibrationProfile(
#            profile_id=str(uuid.uuid4()),
#            profile_name=name,
#            nm_per_pixel=nm_per_pixel,
#            magnification=magnification,
#            detector_type=detector_type,
#            notes=notes,
#        )
#        self.save(p)
#        return p
#
#F 680d3068c7df905729e015573e65b51c5a96b010 40 adept/core/export/__init__.py
## ADEPT export package — created 2026-07-28 (M5-1).
#"""adept.core.export — 結果輸出層：KLARF 寫回、報表、疊圖。
#
#單一匯入點::
#
#    from adept.core.export import (
#        plan_writeback, apply_writeback,      # KLARF 三種寫回模式
#        summarize, write_csv, write_excel,    # 報表
#        render_overlay, write_png,            # 疊圖
#    )
#
#三塊各自的規矩（細節見各模組 docstring）：
#
#- :mod:`.klarf_out` —— ``inplace`` 只改既有欄位且**無損**（沒改到的 byte
#  與原檔逐位元組相同）；``annotate`` 追加 ADCSCORE/ADCCLASS 並保證影像
#  區塊留在列尾；``topn`` 只留高分的並講清楚影像參照怎麼處理。
#- :mod:`.report` —— CSV 是 utf-8-sig，Excel 三張表都由 :func:`summarize`
#  這支純資料函式餵。
#- :mod:`.overlay` —— 純 numpy/cv2 渲染，檔案 IO 只有 :func:`write_png`。
#
#檔案寫入一律 atomic（``.tmp`` + ``os.replace``），且**零 Qt**。
#"""
#from __future__ import annotations
#
#from .klarf_out import (
#    MODES,
#    ExportError,
#    WriteBackPlan,
#    apply_writeback,
#    plan_writeback,
#)
#from .overlay import primary_blob_box, render_overlay, to_display_rgb, write_png
#from .report import feature_keys, summarize, write_csv, write_excel
#
#__all__ = [
#    "ExportError", "WriteBackPlan", "MODES", "plan_writeback", "apply_writeback",
#    "summarize", "write_csv", "write_excel", "feature_keys",
#    "render_overlay", "write_png", "to_display_rgb", "primary_blob_box",
#]
#
#F 801da7f15aff858676f7b2a2826c7c1dc73ecbb7 803 adept/core/export/klarf_out.py
## ADEPT KLARF write-back — authored 2026-07-28 (M5-1).
#"""KLARF 三種寫回模式：inplace / annotate / topn。
#
#角色（見 docs/plans/F0-master-plan.md §7）：pipeline 算完的
#``result_to_json_dict`` 結果（``defect_id`` / ``ok`` / ``score`` / ``bin`` /
#``features``）要回到 KLARF，讓下游（Klarity、review 站）看得到 ADC 的判定。
#
#三種模式各自的承諾
#------------------
#
#``"inplace"`` **只改既有欄位，不動檔案結構**
#    走 :meth:`KlarfDoc.set_cell` 的 span-splice：沒被改到的 byte 與原檔
#    逐位元組相同（鐵則 6）。**什麼都沒改 → 輸出檔與輸入檔位元組完全相同。**
#    要寫的欄位不存在時**直接報錯**（:class:`ExportError`），絕不默默略過
#    —— 使用者以為寫進去了但其實沒有，比報錯糟一百倍。
#
#``"annotate"`` **產生新檔，追加欄位**
#    在欄位定義（1.2 的 ``DefectRecordSpec`` / 1.8 的 ``Columns N { … }``）
#    與每一列 defect 上追加 ``ADCSCORE`` / ``ADCCLASS``（可再加選定的特徵欄）。
#    **影像區塊一律留在最後**：插入點取自
#    :meth:`KlarfDoc.image_layout`（影像 token 的起始欄），新欄位插在它之前，
#    所以 ``IMAGELIST`` / ``Images N { … }`` 仍是列尾 —— 影像對應不會壞。
#    1.2 與 1.8 都支援。
#
#``"topn"`` **產生新檔，只留高分的那幾顆**
#    依 score 由高到低取前 N 顆（或所有 >= ``min_score`` 的），可重新編號
#    DEFECTID，可同時做 annotate 的欄位。
#
#    ★ 影像參照怎麼處理（重要）★
#      - **每列自帶檔名**（1.8 rSEM 的 ``Images N { "檔名" … }``）：檔名跟著
#        列一起走，抽子集後仍指向原本那張圖 —— 完全安全。
#      - **IMAGELIST 帶 TIFF 頁碼**（1.2 EBI patch）：頁碼**原樣保留**，
#        指向**原本那份多頁 TIFF**。DEFECTID 重新編號**不會**連動改頁碼，
#        因為重新編頁等同要重寫 TIFF，本工具不碰原始影像。
#        → 輸出的 KLARF 必須與原 TIFF 放在同一個資料夾才讀得到圖。
#      - **依出現順序連續配頁**（沒有 IMAGELIST 頁碼可用）：抽子集後頁序
#        必然對不上，這種情況會在 ``notes`` 裡明講。
#
#用法::
#
#    plan = plan_writeback(doc, results, "annotate")   # 乾跑，不寫檔
#    print(plan.n_rows_out, plan.columns_added, plan.notes)
#    plan = apply_writeback(doc, results, "annotate", out_path)   # 真的寫
#
#``plan_writeback`` 與 ``apply_writeback`` 走同一條計算路徑，回報的數字
#保證一致；兩者都**不會改動傳進來的 doc**（內部先複製一份）。
#寫檔一律 atomic（``.tmp`` + :func:`os.replace`，鐵則 5）。
#"""
#from __future__ import annotations
#
#import os
#import re
#from dataclasses import dataclass, field
#from typing import Any, Dict, List, Optional, Sequence, Tuple
#
#from ..ingest import klarf_core
#from ..ingest.klarf_core import KlarfDoc
#
#__all__ = [
#    "ExportError", "WriteBackPlan", "MODES",
#    "plan_writeback", "apply_writeback",
#]
#
##: 支援的寫回模式。
#MODES = ("inplace", "annotate", "topn")
#
#_DEFAULT_SCORE_COL = "ADCSCORE"
#_DEFAULT_CLASS_COL = "ADCCLASS"
#
#
#class ExportError(RuntimeError):
#    """匯出失敗（訊息一律寫成使用者看得懂的白話，並附上可行的下一步）。"""
#
#
## ---------------------------------------------------------------------------
## 計畫書
## ---------------------------------------------------------------------------
#@dataclass
#class WriteBackPlan:
#    """「按下去會發生什麼」的預覽。
#
#    - ``mode``             使用的模式（``inplace`` / ``annotate`` / ``topn``）。
#    - ``n_rows_changed``   輸出檔中「內容與原檔不同」的 defect 列數。
#      inplace = 真的有格子被改值的列數；annotate = 全部列（每列都多了欄位）；
#      topn = 被重新編號或被加註記的列數（兩者都關掉時為 0）。
#    - ``columns_touched``  被寫入的**既有**欄位名。
#    - ``columns_added``    新增的欄位名。
#    - ``n_rows_out``       輸出檔的 defect 列數。
#    - ``notes``            白話說明（包含影像參照怎麼處理、對不到的結果…）。
#    - ``issues``           對**輸出結果**跑 :func:`klarf_core.lint` 的
#      :class:`klarf_core.Issue` 清單（寫檔前就算好，所以預覽也看得到）。
#    """
#
#    mode: str
#    n_rows_changed: int = 0
#    columns_touched: List[str] = field(default_factory=list)
#    columns_added: List[str] = field(default_factory=list)
#    n_rows_out: int = 0
#    notes: List[str] = field(default_factory=list)
#    issues: List[Any] = field(default_factory=list)
#
#    def error_issues(self) -> List[Any]:
#        """只取 level == 'error' 的健檢問題（UI 用來決定要不要擋下）。"""
#        return [i for i in self.issues if getattr(i, "level", "") == "error"]
#
#    def to_dict(self) -> Dict[str, Any]:
#        """轉成可 ``json.dumps`` 的 dict（Issue 攤平成欄位）。"""
#        return {
#            "mode": self.mode,
#            "n_rows_changed": int(self.n_rows_changed),
#            "columns_touched": list(self.columns_touched),
#            "columns_added": list(self.columns_added),
#            "n_rows_out": int(self.n_rows_out),
#            "notes": list(self.notes),
#            "issues": [
#                {"code": i.code, "level": i.level, "title": i.title,
#                 "detail": i.detail, "count": i.count, "fixable": i.fixable}
#                for i in self.issues
#            ],
#        }
#
#
## ---------------------------------------------------------------------------
## 小工具
## ---------------------------------------------------------------------------
#def _clone(doc: KlarfDoc) -> KlarfDoc:
#    """複製一份可安全改動的 doc（不動呼叫端傳進來的那份）。
#
#    以 ``doc.to_text()`` 重建：doc 乾淨時字串與原檔完全相同，
#    所以「什麼都沒改 → 位元組相同」的承諾在複製後依然成立。
#    """
#    return KlarfDoc(doc.to_text(), source_path=doc.source_path)
#
#
#def _atomic_write_text(path: str, text: str) -> str:
#    """atomic 寫入文字檔（鐵則 5）。換行沿用文字本身，不做轉換。"""
#    path = str(path)
#    parent = os.path.dirname(os.path.abspath(path))
#    if parent:
#        os.makedirs(parent, exist_ok=True)
#    tmp = path + ".tmp"
#    with open(tmp, "w", encoding="utf-8", newline="") as f:
#        f.write(text)
#    os.replace(tmp, path)
#    return path
#
#
#def _norm_id(v: Any) -> str:
#    """DEFECTID 正規化：``"007"`` 與 ``7`` 視為同一顆。"""
#    s = str(v).strip().strip('"')
#    try:
#        return str(int(s))
#    except (TypeError, ValueError):
#        return s
#
#
#def _num(v: Any, default: float = 0.0) -> float:
#    """安全轉 float（None／非數字 → default）——單一顆的怪值不該炸掉整批。"""
#    try:
#        f = float(v)
#    except (TypeError, ValueError):
#        return float(default)
#    if f != f or f in (float("inf"), float("-inf")):   # nan / inf
#        return float(default)
#    return f
#
#
#def _fmt_float(v: Any, decimals: int) -> str:
#    """固定小數位數（檔案才 diff 得動）。"""
#    return "{:.{d}f}".format(_num(v), d=int(decimals))
#
#
#def _as_int(v: Any, default: int) -> int:
#    try:
#        return int(v)
#    except (TypeError, ValueError):
#        return int(default)
#
#
#def _cols_hint(doc: KlarfDoc) -> str:
#    return (", ".join(doc.defect_columns) if doc.defect_columns
#            else "(column definitions unreadable)")
#
#
#def _require_col(doc: KlarfDoc, name: str, what: str) -> int:
#    """取欄位索引；沒有這欄就報錯（白話 + 可行的下一步）。"""
#    j = doc.col_index(name)
#    if j < 0:
#        raise ExportError(
#            "This KLARF has no \"{name}\" column, so it cannot {what}.\n"
#            "The defect columns in this file are: {cols}.\n"
#            "Point at one of the existing columns instead, or switch to annotate "
#            "mode (which adds columns and writes a new KLARF, leaving the "
#            "original untouched).".format(
#                name=name, what=what, cols=_cols_hint(doc)))
#    return j
#
#
#def _pair_results(doc: KlarfDoc, results: Sequence[Dict[str, Any]]
#                  ) -> Tuple[List[Optional[int]], List[str]]:
#    """把每筆 result 對到 doc.defects 的列索引。
#
#    優先用 DEFECTID 比對；沒有這一欄時退回「第 n 筆對第 n 列」的位置比對
#    並留下警告。回傳 ``(row_idx_per_result, notes)``，對不到的是 ``None``。
#    """
#    notes: List[str] = []
#    di = doc.col_index("DEFECTID")
#    out: List[Optional[int]] = []
#
#    if di < 0:
#        notes.append(
#            "This KLARF has no DEFECTID column, so results are matched to rows "
#            "by position (nth result to nth defect row). If the results are in a "
#            "different order from the KLARF, the mapping will be wrong.")
#        for k in range(len(results)):
#            out.append(k if k < len(doc.defects) else None)
#        if len(results) > len(doc.defects):
#            notes.append("There are {} more results than defect rows in the "
#                         "KLARF; the extras are ignored.".format(
#                len(results) - len(doc.defects)))
#        return out, notes
#
#    exact: Dict[str, int] = {}
#    loose: Dict[str, int] = {}
#    for i, row in enumerate(doc.defects):
#        if di < len(row):
#            exact.setdefault(row[di], i)
#            loose.setdefault(_norm_id(row[di]), i)
#
#    missed = 0
#    for r in results:
#        rid = str(r.get("defect_id", ""))
#        idx = exact.get(rid)
#        if idx is None:
#            idx = loose.get(_norm_id(rid))
#        if idx is None:
#            missed += 1
#        out.append(idx)
#    if missed:
#        notes.append(
#            "{} results have no defect with a matching DEFECTID in this KLARF "
#            "and were skipped (usually the results and the KLARF are not from "
#            "the same wafer — check the source).".format(missed))
#    return out, notes
#
#
## ---------------------------------------------------------------------------
## 欄位定義改寫（annotate / topn 用）
## ---------------------------------------------------------------------------
#_SAFE_COL = re.compile(r"[^A-Z0-9_]")
#
#
#def _feature_col_name(feat: str) -> str:
#    """特徵名 → KLARF 欄位名（大寫、只留 A-Z0-9_）。"""
#    name = _SAFE_COL.sub("_", str(feat).upper()).strip("_")
#    if not name:
#        name = "FEATURE"
#    if name[0].isdigit():
#        name = "F_" + name
#    return name
#
#
#def _insert_pos(doc: KlarfDoc) -> int:
#    """新欄位要插在第幾欄 —— 影像 token 的起始欄之前（沒有影像就接在最後）。"""
#    layout = doc.image_layout()
#    if layout is None:
#        return len(doc.defect_columns)
#    return max(0, min(int(layout[0]), len(doc.defect_columns)))
#
#
#def _rewrite_spec_12(text: str, cols: Sequence[str]) -> str:
#    """改寫 1.2 的 ``DefectRecordSpec N …;``（欄數同時更新）。"""
#    m = re.search(r"DefectRecordSpec\s+\d+\s+[^;]+;", text)
#    if m is None:
#        raise ExportError(
#            "No DefectRecordSpec found, so the column definitions of this "
#            "KLARF 1.2 cannot be read and columns cannot be appended safely. "
#            "Use inplace mode instead.")
#    new = "DefectRecordSpec {} {} ;".format(len(cols), " ".join(cols))
#    return text[:m.start()] + new + text[m.end():]
#
#
#def _rewrite_columns_18(text: str, entries: Sequence[str]) -> str:
#    """改寫 1.8 ``List DefectList`` 內的 ``Columns N { … }``（帶型別的欄位項）。"""
#    dl = re.search(r"List\s+DefectList\s*\{", text)
#    if dl is None:
#        raise ExportError(
#            "No List DefectList found — the structure of this KLARF 1.8 is not "
#            "what was expected, so columns cannot be appended safely. Use "
#            "inplace mode instead.")
#    b0 = text.index("{", dl.start())
#    b1 = klarf_core._find_matching_brace(text, b0)
#    if b1 < 0:
#        raise ExportError(
#            "The braces of the KLARF 1.8 DefectList are not balanced; the file "
#            "may be corrupt.")
#    block = text[b0:b1 + 1]
#    cm = re.search(r"Columns\s+\d+\s*\{[^}]*\}", block)
#    if cm is None:
#        raise ExportError(
#            "No Columns definition inside the KLARF 1.8 DefectList, so columns "
#            "cannot be appended safely. Use inplace mode instead.")
#    lines = []
#    for k in range(0, len(entries), 4):
#        lines.append("  ".join(e + "," for e in entries[k:k + 4]))
#    body = "\n          ".join(lines).rstrip(",")
#    new = "Columns {} {{ {}  }}".format(len(entries), body)
#    block = block[:cm.start()] + new + block[cm.end():]
#    return text[:b0] + block + text[b1 + 1:]
#
#
#def _column_entries_18(doc: KlarfDoc) -> List[str]:
#    """讀出 1.8 現有的 ``Columns`` 欄位項原文（含型別），供插入後重組。"""
#    t = doc._text
#    dl = re.search(r"List\s+DefectList\s*\{", t)
#    if dl is None:
#        return []
#    b0 = t.index("{", dl.start())
#    b1 = klarf_core._find_matching_brace(t, b0)
#    cm = re.search(r"Columns\s+\d+\s*\{([^}]*)\}", t[b0:b1 + 1])
#    if cm is None:
#        return []
#    return [" ".join(c.split()) for c in cm.group(1).split(",") if c.strip()]
#
#
## ---------------------------------------------------------------------------
## annotate：欄位 + 值一起插進去
## ---------------------------------------------------------------------------
#def _annotate(doc: KlarfDoc, results: Sequence[Dict[str, Any]],
#              row_of_result: Sequence[Optional[int]], *,
#              extra_features: Sequence[str] = (),
#              decimals: int = 4,
#              score_col: str = _DEFAULT_SCORE_COL,
#              class_col: str = _DEFAULT_CLASS_COL,
#              missing_score: float = 0.0,
#              missing_class: int = -1,
#              ) -> Tuple[List[str], List[str]]:
#    """在 doc 上插入註記欄與每列的值（就地改 doc）。
#
#    回傳 ``(新增的欄位名, notes)``。影像 token 一律留在列尾。
#    """
#    notes: List[str] = []
#    decimals = max(0, int(decimals))
#    cols = list(doc.defect_columns)
#    if not cols:
#        raise ExportError(
#            "The defect column definitions of this KLARF cannot be read, so no "
#            "columns can be appended. Run the KLARF health check first.")
#
#    new_names = [str(score_col), str(class_col)]
#    feat_cols: List[Tuple[str, str]] = []       # (欄位名, 特徵名)
#    for f in extra_features or ():
#        name = _feature_col_name(f)
#        feat_cols.append((name, str(f)))
#        new_names.append(name)
#        if name != str(f):
#            notes.append("Feature \"{}\" is written as KLARF column \"{}\" "
#                         "(column names allow upper-case letters, digits and "
#                         "underscores only)."
#                         .format(f, name))
#
#    dup = [n for n in new_names if doc.col_index(n) >= 0]
#    if dup:
#        raise ExportError(
#            "This KLARF already has the columns {}, and annotate mode never "
#            "overwrites existing columns.\nUse inplace mode to write into the "
#            "existing columns, or pick an unused column name with score_col= / "
#            "class_col=.".format(", ".join(dup)))
#    if len(set(new_names)) != len(new_names):
#        raise ExportError(
#            "The new column names contain duplicates: {}.".format(
#                ", ".join(new_names)))
#
#    pos = _insert_pos(doc)
#
#    # ---- 每列的值（先算好，才不會邊改邊查）----
#    n_rows = len(doc.defects)
#    vals: List[List[str]] = [
#        [_fmt_float(missing_score, decimals), str(int(missing_class))]
#        + [_fmt_float(missing_score, decimals) for _ in feat_cols]
#        for _ in range(n_rows)
#    ]
#    filled = [False] * n_rows
#    n_missing_feat = 0
#    for r, idx in zip(results, row_of_result):
#        if idx is None or not (0 <= idx < n_rows):
#            continue
#        feats = r.get("features") or {}
#        score = r.get("score")
#        b = r.get("bin")
#        cell = [
#            _fmt_float(missing_score if score is None else score, decimals),
#            str(int(missing_class) if b is None else int(b)),
#        ]
#        for _name, fkey in feat_cols:
#            v = feats.get(fkey)
#            if v is None:
#                n_missing_feat += 1
#                v = missing_score
#            cell.append(_fmt_float(v, decimals))
#        vals[idx] = cell
#        filled[idx] = True
#
#    n_unfilled = sum(1 for f in filled if not f)
#    if n_unfilled:
#        notes.append(
#            "{} defect rows have no matching ADC result; column {} is filled "
#            "with {} and column {} with {} (meaning \"not judged\").".format(
#                n_unfilled, score_col, _fmt_float(missing_score, decimals),
#                class_col, int(missing_class)))
#    if n_missing_feat:
#        notes.append("{} feature values were absent from the results and were "
#                     "filled with {}.".format(
#            n_missing_feat, _fmt_float(missing_score, decimals)))
#
#    # ---- 插欄位名 ----
#    doc.defect_columns = cols[:pos] + list(new_names) + cols[pos:]
#
#    # ---- 插每列的值（影像 token 全部往後推，仍在列尾）----
#    for i, row in enumerate(doc.defects):
#        if len(row) < pos:                       # 壞列：補 0 後再插，不丟資料
#            row.extend(["0"] * (pos - len(row)))
#        doc.defects[i] = row[:pos] + vals[i] + row[pos:]
#    doc._defect_dirty = True
#    doc._img_layout = "unset"                    # 欄位變了，影像佈局快取要重算
#    if doc._il18 is not None and doc._il18 >= pos:
#        doc._il18 += len(new_names)              # 1.8 的 ImageList 欄往後移了
#
#    layout_note = ("The image column is column {}; new columns are inserted "
#                   "before it, so the IMAGELIST / Images block stays at the end "
#                   "of the row.".format(pos + 1))
#    notes.append(layout_note if doc.image_layout() is not None
#                 else "This KLARF has no image column, so new columns are "
#                      "appended at the end.")
#    return list(new_names), notes
#
#
#def _render_new_text(doc: KlarfDoc, new_cols: Sequence[str],
#                     orig_entries18: Sequence[str], pos: int) -> str:
#    """把改過欄位的 doc 產生成新的 KLARF 文字（含欄位定義改寫）。"""
#    text = doc.to_text()
#    if doc._is18:
#        entries = list(orig_entries18)
#        if len(entries) != len(doc.defect_columns) - len(new_cols):
#            raise ExportError(
#                "The KLARF 1.8 Columns definition yields {} columns, which does "
#                "not match the {} that were parsed; aborted to avoid writing a "
#                "broken file.".format(
#                    len(entries), len(doc.defect_columns) - len(new_cols)))
#        typed = []
#        for name in new_cols:
#            typed.append(("int32 " if name.upper() == _DEFAULT_CLASS_COL
#                          else "float32 ") + name)
#        entries = entries[:pos] + typed + entries[pos:]
#        return _rewrite_columns_18(text, entries)
#    return _rewrite_spec_12(text, doc.defect_columns)
#
#
## ---------------------------------------------------------------------------
## 影像參照的說明（topn 用）
## ---------------------------------------------------------------------------
#def _image_notes(doc: KlarfDoc) -> List[str]:
#    """抽子集／重新編號之後，影像參照還有效嗎？—— 一律講清楚。"""
#    notes: List[str] = []
#    if doc.total_image_count() <= 0:
#        notes.append("This KLARF carries no image information, so there are "
#                     "no image references to handle.")
#        return notes
#    if any(doc.defect_image_filename(r) for r in doc.defects):
#        notes.append(
#            "Image references: each defect row carries its own image file name, "
#            "and after subsetting these still point at the original image files "
#            "(paths are relative to the folder holding the KLARF). Put the "
#            "output KLARF in the same folder as the original, or move the images "
#            "along with it.")
#        return notes
#    mode = doc.defect_image_map().get("mode")
#    if mode == "imagelist":
#        notes.append(
#            "Image references: the IMAGELIST TIFF page numbers are kept exactly "
#            "as they are and still point at the original multi-page TIFF. Even "
#            "when DEFECTID is renumbered the page numbers do not follow — "
#            "renumbering pages would mean rewriting the TIFF, and this tool never "
#            "touches the original images. Keep the output KLARF in the same "
#            "folder as the original TIFF.")
#    else:
#        notes.append(
#            "! Image references: in this KLARF the images are paged "
#            "consecutively in defect order (IMAGELIST carries no usable page "
#            "numbers), so after subsetting the page order cannot line up. To keep "
#            "the images, use annotate mode (which keeps every defect), or rewrite "
#            "the TIFF as well (this tool does not).")
#    return notes
#
#
## ---------------------------------------------------------------------------
## 三種模式的實作
## ---------------------------------------------------------------------------
#def _build_inplace(doc: KlarfDoc, results: Sequence[Dict[str, Any]],
#                   *, class_col: Optional[str] = None,
#                   bin_col: Optional[str] = None,
#                   size_col: Optional[str] = None,
#                   size_feature: str = "cd_x_nm",
#                   bin_map: Optional[Dict[Any, Any]] = None,
#                   decimals: int = 4,
#                   skip_failed: bool = True,
#                   ) -> Tuple[str, WriteBackPlan]:
#    plan = WriteBackPlan(mode="inplace")
#    pairs, notes = _pair_results(doc, results)
#    plan.notes.extend(notes)
#
#    targets: List[Tuple[str, str]] = []          # (欄位名, 來源 'bin'/'size')
#    if class_col:
#        _require_col(doc, class_col, "write the bin into the class column")
#        targets.append((str(class_col), "bin"))
#    if bin_col:
#        _require_col(doc, bin_col, "write the bin into the bin column")
#        targets.append((str(bin_col), "bin"))
#    if size_col:
#        _require_col(doc, size_col, "write the size feature into the size column")
#        targets.append((str(size_col), "size"))
#
#    if not targets:
#        plan.notes.append(
#            "No target column was given (class_col / bin_col / size_col are all "
#            "empty), so the output file will be byte-for-byte identical to the "
#            "original.")
#
#    bmap = {str(k): v for k, v in (bin_map or {}).items()}
#    changed_rows = set()
#    n_skipped = 0
#    n_no_bin = 0
#    n_no_feat = 0
#    n_short = 0
#
#    for r, idx in zip(results, pairs):
#        if idx is None:
#            continue
#        if skip_failed and not r.get("ok", True):
#            n_skipped += 1
#            continue
#        row = doc.defects[idx]
#        for name, src in targets:
#            j = doc.col_index(name)
#            if src == "bin":
#                b = r.get("bin")
#                if b is None:
#                    n_no_bin += 1
#                    continue
#                val = str(bmap.get(str(int(b)), int(b)))
#            else:
#                v = (r.get("features") or {}).get(size_feature)
#                if v is None:
#                    n_no_feat += 1
#                    continue
#                val = _fmt_float(v, decimals)
#            if j >= len(row):
#                n_short += 1
#                continue
#            if row[j] != val:
#                doc.set_cell(idx, name, val)
#                changed_rows.add(idx)
#
#    if n_short:
#        plan.notes.append(
#            "{} cells sit in defect rows with fewer tokens than the column "
#            "definition, so there is no cell to write into and they were skipped "
#            "(run the KLARF health check to repair the column count "
#            "first).".format(n_short))
#    if n_skipped:
#        plan.notes.append("{} defects failed to run (ok=False) and were not "
#                          "written back.".format(n_skipped))
#    if n_no_bin:
#        plan.notes.append("{} cells were skipped because the result has no bin "
#                          "value.".format(n_no_bin))
#    if n_no_feat:
#        plan.notes.append("{} cells were skipped because the result has no "
#                          "feature \"{}\".".format(
#            n_no_feat, size_feature))
#
#    plan.columns_touched = [n for n, _s in targets]
#    plan.n_rows_changed = len(changed_rows)
#    plan.n_rows_out = len(doc.defects)
#    text = doc.to_text()
#    plan.issues = klarf_core.lint(doc)
#    return text, plan
#
#
#def _build_annotate(doc: KlarfDoc, results: Sequence[Dict[str, Any]],
#                    **opts: Any) -> Tuple[str, WriteBackPlan]:
#    plan = WriteBackPlan(mode="annotate")
#    pairs, notes = _pair_results(doc, results)
#    plan.notes.extend(notes)
#
#    pos = _insert_pos(doc)
#    entries18 = _column_entries_18(doc) if doc._is18 else []
#    if doc._is18 and not entries18:
#        raise ExportError(
#            "The Columns definition of this KLARF 1.8 cannot be read, so "
#            "columns cannot be appended safely (the file could come out unusable "
#            "downstream). Use inplace mode instead.")
#
#    added, anotes = _annotate(doc, results, pairs, **opts)
#    plan.columns_added = added
#    plan.notes.extend(anotes)
#    plan.n_rows_changed = len(doc.defects)
#    plan.n_rows_out = len(doc.defects)
#
#    text = _render_new_text(doc, added, entries18, pos)
#    plan.issues = klarf_core.lint(klarf_core.load(text))
#    return text, plan
#
#
#def _build_topn(doc: KlarfDoc, results: Sequence[Dict[str, Any]], *,
#                n: int = 0, min_score: Optional[float] = None,
#                renumber: bool = True, include_annotations: bool = True,
#                **annot_opts: Any) -> Tuple[str, WriteBackPlan]:
#    plan = WriteBackPlan(mode="topn")
#    pairs, notes = _pair_results(doc, results)
#    plan.notes.extend(notes)
#
#    n = _as_int(n, 0)
#    if n <= 0 and min_score is None:
#        raise ExportError(
#            "topn mode needs either a count or a score threshold: n = the top N "
#            "by descending score, or min_score = keep defects scoring at least "
#            "this value. With neither, there is no way to tell what to keep.")
#
#    # 影像參照的說明要在抽子集「之前」判斷（子集本身可能就解不出佈局）
#    plan.notes.extend(_image_notes(doc))
#
#    # ---- 挑出候選（有對到列、有分數）----
#    cands: List[Tuple[int, float]] = []
#    n_no_score = 0
#    seen = set()
#    for r, idx in zip(results, pairs):
#        if idx is None or idx in seen:
#            continue
#        s = r.get("score")
#        if s is None:
#            n_no_score += 1
#            continue
#        try:
#            sf = float(s)
#        except (TypeError, ValueError):
#            n_no_score += 1
#            continue
#        seen.add(idx)
#        cands.append((idx, sf))
#    if n_no_score:
#        plan.notes.append(
#            "{} defects have no score (the run failed, or the score is nan) and "
#            "will not appear in the output file."
#            .format(n_no_score))
#
#    order = sorted(range(len(cands)), key=lambda k: (-cands[k][1], cands[k][0]))
#    picked = [cands[k] for k in order]
#    if n > 0:
#        if min_score is not None:
#            plan.notes.append(
#                "Both n={} and min_score={} were given; n wins (the top {} by "
#                "score)."
#                .format(n, min_score, n))
#        picked = picked[:n]
#    else:
#        thr = float(min_score)
#        picked = [p for p in picked if p[1] >= thr]
#        plan.notes.append("Keeping defects scoring >= {}: {} in total.".format(
#            thr, len(picked)))
#
#    keep_rows = [idx for idx, _s in picked]
#    n_before = len(doc.defects)
#    doc.defects = [doc.defects[i] for i in keep_rows]
#    doc._defect_dirty = True
#    doc.summary_stale = True
#    plan.notes.append(
#        "{} defects originally, {} written out (ordered by descending "
#        "score).".format(
#            n_before, len(doc.defects)))
#    plan.notes.append(
#        "SummaryList keeps the original values (it is a whole-wafer statistic, "
#        "and recomputing it would wipe out the real numbers); "
#        "the health check will flag \"summary does not match DefectList count\", "
#        "which is normal for a file that only keeps a subset.")
#
#    n_changed = 0
#    if renumber:
#        di = doc.col_index("DEFECTID")
#        if di < 0:
#            plan.notes.append(
#                "No DEFECTID column, so renumbering was skipped.")
#        else:
#            for k, row in enumerate(doc.defects, 1):
#                if di < len(row):
#                    row[di] = str(k)
#            n_changed = len(doc.defects)
#            plan.columns_touched.append(doc.defect_columns[di])
#            plan.notes.append("DEFECTID renumbered to 1..{}.".format(
#                len(doc.defects)))
#    else:
#        plan.notes.append(
#            "DEFECTID keeps the original values (no renumbering).")
#
#    pos = _insert_pos(doc)
#    entries18 = _column_entries_18(doc) if doc._is18 else []
#    if include_annotations:
#        if doc._is18 and not entries18:
#            raise ExportError(
#                "The Columns definition of this KLARF 1.8 cannot be read, so "
#                "annotation columns cannot be appended. Use "
#                "include_annotations=False to filter only.")
#        # 列索引已經因為抽子集而改變：舊列索引 → 新列索引
#        new_of_old = {old: new for new, old in enumerate(keep_rows)}
#        sub_pairs = [None if p is None else new_of_old.get(p) for p in pairs]
#        added, anotes = _annotate(doc, results, sub_pairs, **annot_opts)
#        plan.columns_added = added
#        plan.notes.extend(anotes)
#        n_changed = len(doc.defects)
#        text = _render_new_text(doc, added, entries18, pos)
#    else:
#        text = doc.to_text()
#
#    plan.n_rows_changed = n_changed
#    plan.n_rows_out = len(doc.defects)
#    plan.issues = klarf_core.lint(klarf_core.load(text))
#    return text, plan
#
#
#_BUILDERS = {
#    "inplace": _build_inplace,
#    "annotate": _build_annotate,
#    "topn": _build_topn,
#}
#
#
#def _build(doc: KlarfDoc, results: Sequence[Dict[str, Any]], mode: str,
#           **opts: Any) -> Tuple[str, WriteBackPlan]:
#    mode = str(mode).strip().lower()
#    if mode not in _BUILDERS:
#        raise ExportError(
#            "Unrecognised write-back mode \"{}\". Available: {} "
#            "(inplace = edit existing columns only, annotate = add columns, "
#            "topn = keep the highest scoring only)."
#            .format(mode, ", ".join(MODES)))
#    if doc is None:
#        raise ExportError(
#            "No KLARF was given — load a KLARF before writing back.")
#    work = _clone(doc)
#    try:
#        return _BUILDERS[mode](work, list(results or []), **opts)
#    except TypeError as e:                       # 參數打錯 → 講清楚哪個模式吃哪些參數
#        if "unexpected keyword argument" in str(e):
#            raise ExportError(
#                "Mode \"{}\" received an option it does not understand: "
#                "{}.".format(mode, e)) from None
#        raise
#
#
## ---------------------------------------------------------------------------
## 對外 API
## ---------------------------------------------------------------------------
#def plan_writeback(doc: KlarfDoc, results: Sequence[Dict[str, Any]], mode: str,
#                   **opts: Any) -> WriteBackPlan:
#    """乾跑：算出「按下去會發生什麼」，**不寫任何檔案、不改動 doc**。
#
#    參數與 :func:`apply_writeback` 完全相同（少一個 ``out_path``），
#    回報的數字也保證一致 —— 兩者走同一條計算路徑。
#    """
#    _text, plan = _build(doc, results, mode, **opts)
#    return plan
#
#
#def apply_writeback(doc: KlarfDoc, results: Sequence[Dict[str, Any]], mode: str,
#                    out_path: str, **opts: Any) -> WriteBackPlan:
#    """真的寫出 KLARF（atomic），回傳與 :func:`plan_writeback` 相同的計畫書。
#
#    各模式的選項
#    ------------
#    ``inplace``
#        ``class_col`` / ``bin_col``（把 bin 寫進這些既有欄位，例如
#        ``CLASSNUMBER`` / ``ROUGHBINNUMBER`` / ``FINEBINNUMBER``）、
#        ``size_col``（把 ``size_feature`` 寫進去，例如 ``DSIZE``）、
#        ``size_feature``（預設 ``"cd_x_nm"``）、``bin_map``
#        （``{bin: 要寫的值}``，預設原樣寫）、``decimals``（預設 4）、
#        ``skip_failed``（預設 True：ok=False 的不寫）。
#        指定的欄位不存在 → :class:`ExportError`。
#        全部都不指定 → 輸出檔與原檔**逐位元組相同**。
#
#    ``annotate``
#        ``extra_features``（要另外寫成欄位的特徵名 list）、``decimals``
#        （預設 4）、``score_col`` / ``class_col``（預設 ``ADCSCORE`` /
#        ``ADCCLASS``）、``missing_score`` / ``missing_class``
#        （沒有結果的列填什麼，預設 0.0 / -1）。
#
#    ``topn``
#        ``n``（取前幾顆，0=改用 min_score）、``min_score``、``renumber``
#        （預設 True）、``include_annotations``（預設 True，會一併做
#        annotate 的欄位），加上 annotate 的所有選項。
#    """
#    text, plan = _build(doc, results, mode, **opts)
#    _atomic_write_text(str(out_path), text)
#    return plan
#
#F eeb80b55a38476ef2f80a5e10538a50bc935aa1b 292 adept/core/export/overlay.py
## ADEPT overlay rendering — authored 2026-07-28 (M5-1).
#"""缺陷疊圖：把「機器看到什麼」畫成一張人看得懂的圖。
#
#純 numpy/cv2，**不碰檔案**（除了 :func:`write_png`）—— 這樣 Studio 的
#Gallery、CLI 的批次出圖、報表的插圖都能共用同一支渲染函式。
#
#:func:`render_overlay` 產出 RGB uint8 面板：
#
#- 底圖取 ``images["test"]``（EBI patch）或 ``images["single"]``（rSEM）；
#- 主 blob 的 bounding box 畫**紅框**；
#- 左上角可疊一行標籤（score / bin …），底下鋪半透明深色條方便閱讀；
#- ``images`` 裡有 ``"diff"`` 時輸出 **[test | diff] 並排**（寬度剛好兩倍）。
#
#★ 字型限制 ★
#  cv2 內建的 Hershey 字型**沒有中日韓字元**。標籤裡的非 ASCII 字元會被
#  換成 ``?`` 再畫（不會炸、不會亂碼）。要中文標籤請在 UI 層用 Qt 畫。
#
#批次執行時 Context 不會保留（記憶體會爆），所以這裡**不提供**
#``save_overlays(results_with_ctx, ...)``；改由呼叫端逐顆
#``render_overlay`` → :func:`write_png`，要畫哪幾顆由 UI/CLI 決定。
#"""
#from __future__ import annotations
#
#import os
#from typing import Any, Dict, Optional, Sequence, Tuple
#
#import cv2
#import numpy as np
#
#from .klarf_out import ExportError
#
#__all__ = ["render_overlay", "write_png", "to_display_rgb",
#           "primary_blob_box", "BOX_COLOR"]
#
##: 主 blob 外框的顏色（RGB）。
#BOX_COLOR = (255, 32, 32)
##: 標籤文字顏色（RGB）與底條顏色。
#TEXT_COLOR = (255, 255, 255)
#BANNER_COLOR = (0, 0, 0)
#
##: 底圖的挑選順序（第一個找得到的就用）。
#BASE_PRIORITY = ("test", "single", "aligned", "ref", "diff")
#
#_FONT = cv2.FONT_HERSHEY_SIMPLEX
#
#
## ---------------------------------------------------------------------------
## 小工具
## ---------------------------------------------------------------------------
#def _ascii_only(text: str) -> str:
#    """非 ASCII → '?'（cv2 的內建字型畫不出 CJK，但也不該讓它炸）。"""
#    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(text))
#
#
#def to_display_rgb(arr: np.ndarray) -> np.ndarray:
#    """任意 2-D/3-D 陣列 → 可顯示的 RGB uint8（float 圖自動拉伸到 0–255）。"""
#    a = np.asarray(arr)
#    if a.ndim == 3 and a.shape[2] == 1:
#        a = a[:, :, 0]
#    if a.ndim not in (2, 3):
#        raise ExportError(
#            "Overlays accept a 2-D grayscale or 3-channel colour image only; got shape {}.".format(a.shape))
#    if a.ndim == 3 and a.shape[2] not in (3, 4):
#        raise ExportError(
#            "Overlays accept 3- or 4-channel colour images only; got {} channels.".format(a.shape[2]))
#
#    if a.dtype != np.uint8:
#        f = a.astype(np.float32)
#        lo = float(np.nanmin(f)) if f.size else 0.0
#        hi = float(np.nanmax(f)) if f.size else 1.0
#        f = np.nan_to_num(f, nan=lo, posinf=hi, neginf=lo)
#        if hi - lo < 1e-12:
#            a = np.zeros(f.shape, np.uint8)
#        else:
#            # 四捨五入（不是無條件捨去）：最大值才會剛好落在 255
#            a = np.clip(np.rint((f - lo) * (255.0 / (hi - lo))),
#                        0, 255).astype(np.uint8)
#
#    if a.ndim == 2:
#        return cv2.cvtColor(a, cv2.COLOR_GRAY2RGB)
#    if a.shape[2] == 4:
#        return cv2.cvtColor(a, cv2.COLOR_RGBA2RGB)
#    return np.ascontiguousarray(a)
#
#
#def _blob_box(b: Any) -> Optional[Tuple[int, int, int, int]]:
#    """blob（dict 或 DefectROI）→ (x, y, w, h)。"""
#    if b is None:
#        return None
#    if isinstance(b, dict):
#        if not all(k in b for k in ("x", "y", "w", "h")):
#            return None
#        vals = (b["x"], b["y"], b["w"], b["h"])
#    elif hasattr(b, "bbox"):
#        vals = tuple(b.bbox)
#    elif all(hasattr(b, k) for k in ("x", "y", "w", "h")):
#        vals = (b.x, b.y, b.w, b.h)
#    elif isinstance(b, (tuple, list)) and len(b) >= 4:
#        vals = tuple(b[:4])
#    else:
#        return None
#    try:
#        return (int(vals[0]), int(vals[1]), int(vals[2]), int(vals[3]))
#    except (TypeError, ValueError):
#        return None
#
#
#def _blob_rank(b: Any) -> float:
#    """主 blob 的挑選依據：SNR 最強者；沒有 SNR 就用面積。"""
#    if isinstance(b, dict):
#        v = b.get("snr_value", b.get("area", 0.0))
#    else:
#        v = getattr(b, "snr_value", getattr(b, "area", 0.0))
#    try:
#        return float(v)
#    except (TypeError, ValueError):
#        return 0.0
#
#
#def primary_blob_box(blobs: Optional[Sequence[Any]] = None,
#                     features: Optional[Dict[str, Any]] = None
#                     ) -> Optional[Tuple[int, int, int, int]]:
#    """挑出「主 blob」的框：blobs 裡 SNR 最強的那塊；
#
#    blobs 是空的時候，退而求其次看 features 有沒有
#    ``blob_x`` / ``blob_y`` / ``blob_w`` / ``blob_h``。都沒有回 None。
#    """
#    best = None
#    best_rank = None
#    for b in (blobs or ()):
#        box = _blob_box(b)
#        if box is None:
#            continue
#        rank = _blob_rank(b)
#        if best_rank is None or rank > best_rank:
#            best, best_rank = box, rank
#    if best is not None:
#        return best
#    f = features or {}
#    if all(k in f for k in ("blob_x", "blob_y", "blob_w", "blob_h")):
#        return _blob_box({k[5:]: f[k] for k in
#                          ("blob_x", "blob_y", "blob_w", "blob_h")})
#    return None
#
#
#def _pick_base(images: Dict[str, Any]) -> Tuple[str, np.ndarray]:
#    for k in BASE_PRIORITY:
#        if k in images and images[k] is not None:
#            return k, images[k]
#    for k in sorted(images):
#        if images[k] is not None:
#            return k, images[k]
#    raise ExportError(
#        "This defect has no image to draw (images is empty). Check that the "
#        "load card in the pipeline ran successfully.")
#
#
#def _draw_box(panel: np.ndarray, box: Tuple[int, int, int, int],
#              color: Tuple[int, int, int] = BOX_COLOR) -> None:
#    """在 panel 上畫框（超出邊界會被裁到圖內，至少留 1 px 寬高）。"""
#    h, w = panel.shape[:2]
#    x, y, bw, bh = box
#    x0 = max(0, min(int(x), w - 1))
#    y0 = max(0, min(int(y), h - 1))
#    x1 = max(x0, min(int(x) + max(1, int(bw)) - 1, w - 1))
#    y1 = max(y0, min(int(y) + max(1, int(bh)) - 1, h - 1))
#    thick = 1 if min(h, w) < 192 else 2
#    cv2.rectangle(panel, (x0, y0), (x1, y1), tuple(int(c) for c in color), thick)
#
#
#def _draw_label(panel: np.ndarray, label: str) -> None:
#    """左上角一行標籤（深色底條 + 白字）。非 ASCII 會變成 '?'。"""
#    text = _ascii_only(label).strip()
#    if not text:
#        return
#    h, w = panel.shape[:2]
#    scale = max(0.35, min(0.6, w / 320.0))
#    thick = 1
#    (tw, th), base = cv2.getTextSize(text, _FONT, scale, thick)
#    pad = 3
#    bh = min(h, th + base + 2 * pad)
#    band = panel[0:bh, 0:min(w, tw + 2 * pad)]
#    if band.size:
#        band[:] = (band.astype(np.uint16) * 1 // 4).astype(np.uint8)  # 壓暗當底
#    cv2.putText(panel, text, (pad, pad + th), _FONT, scale,
#                tuple(int(c) for c in TEXT_COLOR), thick, cv2.LINE_AA)
#
#
## ---------------------------------------------------------------------------
## 主函式
## ---------------------------------------------------------------------------
#def render_overlay(images: Dict[str, Any],
#                   features: Optional[Dict[str, Any]] = None, *,
#                   blobs: Optional[Sequence[Any]] = None,
#                   box: Optional[Sequence[int]] = None,
#                   label: Optional[str] = None,
#                   base_key: Optional[str] = None,
#                   diff_key: str = "diff",
#                   montage: bool = True) -> np.ndarray:
#    """把一顆 defect 畫成 RGB uint8 面板。
#
#    參數
#    ----
#    images
#        Context 的影像 dict（或其子集）。底圖依 ``test`` → ``single`` →
#        ``aligned`` → ``ref`` → ``diff`` 的順序挑第一個找得到的；
#        ``base_key`` 可以指定。
#    features
#        該顆的特徵 dict。兩個用途：(1) ``box`` 與 ``blobs`` 都沒給時，
#        若含 ``blob_x/blob_y/blob_w/blob_h`` 就用它畫框；(2) ``label``
#        沒給但含 ``score`` 時自動組出 ``score=…`` 標籤。
#    blobs
#        ``ctx.meta["blobs"]``（dict 清單）或 ``DefectROI`` 清單；
#        取 SNR 最強的那塊畫紅框。
#    box
#        直接指定 ``(x, y, w, h)``，優先於 ``blobs`` / ``features``。
#    label
#        左上角文字（非 ASCII 會顯示成 ``?``，見模組 docstring）。
#    montage
#        ``images`` 有 ``diff`` 時是否輸出 **[底圖 | diff] 並排**
#        （預設 True，寬度剛好是底圖的兩倍）。
#
#    回傳 ``(H, W, 3)`` 或 ``(H, 2W, 3)`` 的 uint8 RGB 陣列。
#    """
#    if not isinstance(images, dict) or not images:
#        raise ExportError(
#            "render_overlay needs a dict of images (e.g. ctx.images); it got an empty one.")
#    features = dict(features or {})
#
#    if base_key is not None:
#        if base_key not in images or images[base_key] is None:
#            raise ExportError(
#                "The requested base image stream \"{}\" does not exist; this defect has: {}.".format(
#                    base_key, ", ".join(sorted(images))))
#        base = images[base_key]
#    else:
#        base_key, base = _pick_base(images)
#
#    left = to_display_rgb(base)
#    h, w = left.shape[:2]
#
#    the_box = _blob_box(box) if box is not None else primary_blob_box(blobs, features)
#    if the_box is not None:
#        _draw_box(left, the_box)
#
#    panel = left
#    right_src = images.get(diff_key)
#    if montage and diff_key != base_key and right_src is not None:
#        right = to_display_rgb(right_src)
#        if right.shape[:2] != (h, w):
#            right = cv2.resize(right, (w, h), interpolation=cv2.INTER_NEAREST)
#        if the_box is not None:
#            _draw_box(right, the_box)
#        panel = np.concatenate([left, right], axis=1)
#        panel[:, w:w + 1] = 96          # 中間一條細分隔線（不改變總寬度）
#
#    if label is None:
#        s = features.get("score")
#        if s is not None:
#            try:
#                label = "score={:.3f}".format(float(s))
#            except (TypeError, ValueError):
#                label = None
#    if label:
#        _draw_label(panel, str(label))
#
#    return np.ascontiguousarray(panel.astype(np.uint8))
#
#
#def write_png(arr: np.ndarray, path: str) -> str:
#    """把疊圖存成 PNG —— atomic（``.tmp`` + :func:`os.replace`）、CJK 路徑安全。
#
#    走 ``cv2.imencode`` + ``ndarray.tofile``（``cv2.imwrite`` 在 Windows
#    吃不到含中日韓字元的路徑）。輸入是 RGB，寫檔前轉成 cv2 要的 BGR。
#    """
#    path = str(path)
#    parent = os.path.dirname(os.path.abspath(path))
#    if parent:
#        os.makedirs(parent, exist_ok=True)
#    a = np.asarray(arr)
#    if a.dtype != np.uint8 or a.ndim not in (2, 3):
#        a = to_display_rgb(a)
#    if a.ndim == 3 and a.shape[2] == 3:
#        a = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
#    ok, buf = cv2.imencode(".png", a)
#    if not ok:      # pragma: no cover — PNG 編碼失敗實務上只在記憶體不足時發生
#        raise ExportError("PNG encoding failed; cannot write {}.".format(path))
#    tmp = path + ".tmp"
#    buf.tofile(tmp)
#    os.replace(tmp, path)
#    return path
#
