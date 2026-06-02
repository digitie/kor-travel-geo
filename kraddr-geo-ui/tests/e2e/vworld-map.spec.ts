import { expect, test, type Page } from "@playwright/test";
import { inflateSync } from "node:zlib";

test.describe("VWorld 지도", () => {
  test("debug geocode page를 반복 진입해도 첫 화면이 렌더링된다", async ({
    page
  }) => {
    for (let index = 0; index < 8; index += 1) {
      await page.goto("/debug/geocode", { waitUntil: "domcontentloaded" });

      await expect(page.getByRole("heading", { name: "Geocode" })).toBeVisible({
        timeout: 15_000
      });
      await expect(page.getByText("This page couldn")).toHaveCount(0);
    }
  });

  test("Python API .env의 VWorld 키로 geocode 지도 canvas와 WMTS 타일을 로드한다", async ({
    page
  }) => {
    const consoleMessages: string[] = [];
    page.on("console", (message) => {
      consoleMessages.push(redactVWorldUrl(message.text()));
    });
    const geocodeResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/api/proxy/v2/geocode") &&
        response.request().method() === "POST" &&
        response.status() >= 200 &&
        response.status() < 400,
      { timeout: 30_000 }
    );
    const runtimeConfig = page.waitForResponse("**/api/runtime-config");

    await page.goto("/debug/geocode");

    const runtimePayload = (await (await runtimeConfig).json()) as {
      vworldApiKey?: unknown;
    };
    expect(typeof runtimePayload.vworldApiKey).toBe("string");
    expect((runtimePayload.vworldApiKey as string).trim().length).toBeGreaterThan(0);
    await expectVWorldBaseTileFetch(page, runtimePayload.vworldApiKey as string);

    await page.getByRole("button", { name: "실행" }).click();
    await geocodeResponse;

    await expect(page.getByTestId("vworld-map-container")).toBeVisible({
      timeout: 15_000
    });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible({
      timeout: 15_000
    });
    await page.waitForTimeout(1500);

    const mapScreenshot = await page.getByTestId("vworld-map-container").screenshot();
    const screenshotStats = pngColorStats(mapScreenshot);
    expect(screenshotStats.uniqueColorBuckets, JSON.stringify(screenshotStats)).toBeGreaterThan(
      40
    );
    expect(screenshotStats.nonWhiteSamples, JSON.stringify(screenshotStats)).toBeGreaterThan(200);
    expect(
      consoleMessages.some(
        (message) => message.includes("CORS request not http") || message.includes("vworld://")
      ),
      consoleMessages.join("\n")
    ).toBe(false);

    await page.locator(".maplibregl-canvas").click({ position: { x: 120, y: 120 } });
    await expect(page.getByRole("heading", { name: "Geocode" })).toBeVisible();
    await expect(page.getByText("지도 타일 로딩이 불안정합니다")).toHaveCount(0);
    await expect(page.getByText("This page couldn")).toHaveCount(0);
  });
});

async function expectVWorldBaseTileFetch(page: Page, apiKey: string) {
  const tile = await page.evaluate(async (key) => {
    const z = 15;
    const lon = 126.978;
    const lat = 37.5665;
    const scale = 2 ** z;
    const x = Math.floor(((lon + 180) / 360) * scale);
    const latRad = (lat * Math.PI) / 180;
    const y = Math.floor(
      ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) *
        scale
    );
    const response = await fetch(
      `https://api.vworld.kr/req/wmts/1.0.0/${encodeURIComponent(key)}/Base/${z}/${y}/${x}.png`
    );
    return {
      contentType: response.headers.get("content-type"),
      size: (await response.arrayBuffer()).byteLength,
      status: response.status
    };
  }, apiKey);

  expect(tile.status).toBeGreaterThanOrEqual(200);
  expect(tile.status).toBeLessThan(400);
  expect(tile.contentType ?? "").toContain("image");
  expect(tile.size).toBeGreaterThan(1000);
}

function redactVWorldUrl(value: string) {
  return value.replace(/(\/req\/wmts\/1\.0\.0\/)([^/?#]+)(\/)/g, "$1***$3");
}

function pngColorStats(buffer: Buffer) {
  const image = decodePng(buffer);
  const uniqueColors = new Set<string>();
  let nonWhiteSamples = 0;
  let samples = 0;

  for (let y = 20; y < image.height - 20; y += 8) {
    for (let x = 20; x < image.width - 20; x += 8) {
      const offset = (y * image.width + x) * 4;
      const red = image.rgba[offset];
      const green = image.rgba[offset + 1];
      const blue = image.rgba[offset + 2];
      const alpha = image.rgba[offset + 3];
      if (alpha < 10) continue;

      samples += 1;
      uniqueColors.add(`${red >> 3}:${green >> 3}:${blue >> 3}`);
      if (!(red > 238 && green > 238 && blue > 238)) {
        nonWhiteSamples += 1;
      }
    }
  }

  return {
    height: image.height,
    nonWhiteSamples,
    samples,
    uniqueColorBuckets: uniqueColors.size,
    width: image.width
  };
}

function decodePng(buffer: Buffer) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  expect(buffer.subarray(0, signature.length).equals(signature)).toBe(true);

  let offset = signature.length;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idatChunks: Buffer[] = [];

  while (offset < buffer.length) {
    const chunkLength = buffer.readUInt32BE(offset);
    const chunkType = buffer.subarray(offset + 4, offset + 8).toString("ascii");
    const chunkData = buffer.subarray(offset + 8, offset + 8 + chunkLength);
    offset += 12 + chunkLength;

    if (chunkType === "IHDR") {
      width = chunkData.readUInt32BE(0);
      height = chunkData.readUInt32BE(4);
      bitDepth = chunkData[8];
      colorType = chunkData[9];
    } else if (chunkType === "IDAT") {
      idatChunks.push(chunkData);
    } else if (chunkType === "IEND") {
      break;
    }
  }

  expect(bitDepth).toBe(8);
  expect([2, 6]).toContain(colorType);

  const channels = colorType === 6 ? 4 : 3;
  const rowLength = width * channels;
  const inflated = inflateSync(Buffer.concat(idatChunks));
  const rgba = Buffer.alloc(width * height * 4);
  let sourceOffset = 0;
  let previous = Buffer.alloc(rowLength);

  for (let y = 0; y < height; y += 1) {
    const filter = inflated[sourceOffset];
    sourceOffset += 1;
    const row = Buffer.from(inflated.subarray(sourceOffset, sourceOffset + rowLength));
    sourceOffset += rowLength;
    unfilterRow(row, previous, channels, filter);

    for (let x = 0; x < width; x += 1) {
      const source = x * channels;
      const target = (y * width + x) * 4;
      rgba[target] = row[source];
      rgba[target + 1] = row[source + 1];
      rgba[target + 2] = row[source + 2];
      rgba[target + 3] = channels === 4 ? row[source + 3] : 255;
    }
    previous = row;
  }

  return { height, rgba, width };
}

function unfilterRow(row: Buffer, previous: Buffer, bytesPerPixel: number, filter: number) {
  for (let index = 0; index < row.length; index += 1) {
    const left = index >= bytesPerPixel ? row[index - bytesPerPixel] : 0;
    const up = previous[index] ?? 0;
    const upLeft = index >= bytesPerPixel ? previous[index - bytesPerPixel] : 0;

    if (filter === 1) {
      row[index] = (row[index] + left) & 0xff;
    } else if (filter === 2) {
      row[index] = (row[index] + up) & 0xff;
    } else if (filter === 3) {
      row[index] = (row[index] + Math.floor((left + up) / 2)) & 0xff;
    } else if (filter === 4) {
      row[index] = (row[index] + paethPredictor(left, up, upLeft)) & 0xff;
    } else {
      expect(filter).toBe(0);
    }
  }
}

function paethPredictor(left: number, up: number, upLeft: number) {
  const estimate = left + up - upLeft;
  const leftDistance = Math.abs(estimate - left);
  const upDistance = Math.abs(estimate - up);
  const upLeftDistance = Math.abs(estimate - upLeft);

  if (leftDistance <= upDistance && leftDistance <= upLeftDistance) return left;
  if (upDistance <= upLeftDistance) return up;
  return upLeft;
}
