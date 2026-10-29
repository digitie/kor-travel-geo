import { expect, test } from "@playwright/test";
import { installSourceFilesMock, makeCategoryCatalog, makeUploadSession } from "./fixtures/source-files";

test("등록 그룹을 명시적으로 선택하고 혼합 기준월을 확인해 매칭 세트 초안을 만든다", async ({ page }) => {
  const sources = [
    ["roadname_hangul_full", "도로명주소 한글 전체분", "202609"],
    ["locsum_full", "위치정보요약DB_전체분", "202609"],
    ["navi_full", "내비게이션용DB_전체분", "202609"],
    ["electronic_map_full", "도로명주소 전자지도", "202610"]
  ];
  const categories = sources.slice(1).map(([category, label]) => ({category,label,role:"build_required",serving_usage:"serving_core",group_kind:"single_file",optional:false,expected_member_kinds:[]}));
  const sessions = sources.map(([category,,user_yyyymm]) => makeUploadSession({category,user_yyyymm,upload_session_id:category,state:"registered",registration_state:"registered"}));
  const notRegistered = makeUploadSession({upload_session_id:"unregistered",source_file_group_id:"forbidden-group",state:"uploading"});
  await installSourceFilesMock(page,{catalog:makeCategoryCatalog(categories),uploadSessions:[...sessions,notRegistered]});
  let created: Record<string, unknown> | null = null;
  await page.route("**/api/proxy/v1/admin/source-match-sets**",async(route)=>{
    const request = route.request();
    if (request.method()==="POST" && new URL(request.url()).pathname.endsWith("/source-match-sets")) {
      const body=request.postDataJSON();
      created={match_set:{source_match_set_id:"ms_new",...body,state:"draft",mixed_yyyymm:true,integrity_alert:false,created_at:"2026-10-29T00:00:00Z",updated_at:"2026-10-29T00:00:00Z"},items:body.items};
      return route.fulfill({json:created});
    }
    if (created && new URL(request.url()).pathname.endsWith("/ms_new")) return route.fulfill({json:created});
    await route.fallback();
  });
  await page.goto("/admin/source-files");
  await page.getByRole("tab",{name:"매칭 세트",exact:true}).click();
  await page.getByRole("button",{name:"새 매칭 세트 만들기",exact:true}).click();
  await page.getByRole("textbox",{name:"매칭 세트 이름",exact:true}).fill("202610 원천 업데이트");
  await page.getByRole("combobox",{name:"구성 프로파일",exact:true}).selectOption("serving_minimal");
  const submit=page.getByRole("button",{name:"초안 생성",exact:true});
  await expect(submit).toBeDisabled();
  await expect(page.locator('option[value="forbidden-group"]')).toHaveCount(0);
  for (const [category,label] of sources) await page.getByRole("combobox",{name:`${label} (필수)`,exact:true}).selectOption(`grp_${category}`);
  await expect(submit).toBeDisabled();
  await page.getByRole("checkbox",{name:/자료별 기준월이 다른 구성을 확인했습니다/}).check();
  const request=page.waitForRequest(r=>r.method()==="POST"&&new URL(r.url()).pathname.endsWith("/source-match-sets"));
  await submit.click();
  const body=(await request).postDataJSON();
  expect(body.profile).toBe("serving_minimal");
  expect(body.items.map((item:{source_file_group_id:string})=>item.source_file_group_id)).toEqual(sources.map(([category])=>`grp_${category}`));
  expect(body.items.map((item:{effective_yyyymm:string})=>item.effective_yyyymm)).toEqual(sources.map((source)=>source[2]));
  expect(body.metadata.mixed_yyyymm_acknowledged).toBe(true);
  await expect(page.getByRole("heading",{name:"202610 원천 업데이트",exact:true})).toBeVisible();
});
