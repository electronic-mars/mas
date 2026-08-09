const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const root = path.resolve(__dirname, "..");
const folder = path.join(
  root,
  "assets",
  "icon_concepts",
  "selected_variant_04",
  "hugeicons_style",
);

const concepts = [
  ["01-stroke-rounded.svg", "01", "Stroke Rounded", "1.5 px · recommended"],
  ["02-stroke-compact.svg", "02", "Stroke Compact", "shorter orbit · small UI"],
  ["03-stroke-technical.svg", "03", "Stroke Technical", "8 mounting holes"],
  ["04-duotone-rounded.svg", "04", "Duotone Rounded", "orange secondary orbit"],
  ["05-bulk-rounded.svg", "05", "Bulk Rounded", "soft layered mass"],
  ["06-solid-rounded.svg", "06", "Solid Rounded", "active / selected state"],
];

const cardWidth = 346;
const cardHeight = 292;
const gap = 24;
const startX = 56;
const startY = 152;

const cards = concepts.map(([, number, name, note], index) => {
  const column = index % 3;
  const row = Math.floor(index / 3);
  const x = startX + column * (cardWidth + gap);
  const y = startY + row * (cardHeight + gap);
  return `
    <rect x="${x}" y="${y}" width="${cardWidth}" height="${cardHeight}" rx="22" fill="#ffffff" stroke="#dedfdd"/>
    <text x="${x + 30}" y="${y + 230}" fill="#9a9da2" font-size="12">${number}</text>
    <text x="${x + 30}" y="${y + 256}" fill="#1b1e23" font-size="16" font-weight="650">${name}</text>
    <text x="${x + 30}" y="${y + 278}" fill="#8a8e94" font-size="12">${note}</text>`;
}).join("");

const layout = Buffer.from(`
  <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="820">
    <rect width="1200" height="820" fill="#f7f7f5"/>
    <text x="56" y="76" fill="#1b1e23" font-family="Segoe UI, sans-serif" font-size="30" font-weight="650">Mini Audio Switcher</text>
    <text x="56" y="108" fill="#666b73" font-family="Segoe UI, sans-serif" font-size="15">Original Saturn-speaker mark translated into a 24×24 rounded icon language.</text>
    <g font-family="Segoe UI, sans-serif">${cards}</g>
  </svg>`);

async function main() {
  const composites = [{ input: layout, left: 0, top: 0 }];
  for (let index = 0; index < concepts.length; index += 1) {
    const [file] = concepts[index];
    const stem = path.basename(file, ".svg");
    const pngFolder = path.join(folder, "png", stem);
    fs.mkdirSync(pngFolder, { recursive: true });
    for (const size of [24, 48, 96]) {
      await sharp(path.join(folder, file))
        .resize(size, size)
        .png()
        .toFile(path.join(pngFolder, `${stem}_${size}.png`));
    }
    const column = index % 3;
    const row = Math.floor(index / 3);
    const left = startX + column * (cardWidth + gap) + 97;
    const top = startY + row * (cardHeight + gap) + 30;
    const icon = await sharp(path.join(folder, file))
      .resize(152, 152)
      .png()
      .toBuffer();
    composites.push({ input: icon, left, top });
  }
  await sharp({
    create: {
      width: 1200,
      height: 820,
      channels: 4,
      background: "#f7f7f5",
    },
  })
    .composite(composites)
    .png()
    .toFile(path.join(folder, "hugeicons_style_variants.png"));
  console.log(path.join(folder, "hugeicons_style_variants.png"));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
