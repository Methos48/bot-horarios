import { ReplitConnectors } from "@replit/connectors-sdk";

const WORKBOOK_NAME = "Calculadora de RAID.xlsm";
const WORKBOOK_PATHS = [
  process.env.ONEDRIVE_WORKBOOK_PATH,
  "Proyecto/Calculadora de RAID.xlsm",
].filter(Boolean);
const REQUIRED_WORKSHEET = "CALCULADORA";
const RAID_HEADER = "RAID";
const CURRENT_DATE_HEADER = "FECHA HORA ACTUAL";

const connectors = new ReplitConnectors();

function normalize(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, " ")
    .trim();
}

function compact(value) {
  return normalize(value).replace(/\s+/g, "");
}

function usedRangeStartRow(address) {
  const match = String(address || "").match(/![A-Z]+(\d+):/i);
  return match ? Number(match[1]) : 1;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function lineContainsBoss(line, boss) {
  const normalizedLine = normalize(line);
  const normalizedBoss = normalize(boss);
  if (!normalizedLine || !normalizedBoss) return false;

  const pattern = new RegExp(
    `(?:^|\\s)${escapeRegExp(normalizedBoss)}(?:$|\\s)`,
  );
  return pattern.test(normalizedLine);
}

function parseExcelDateTime(dateText, hourText, minuteText, secondText = "0") {
  const [dayText, monthText, yearText] = dateText.split(/[\/.-]/);
  const day = Number(dayText);
  const month = Number(monthText);
  const year = yearText.length === 2 ? 2000 + Number(yearText) : Number(yearText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);

  if (
    !Number.isInteger(day) ||
    !Number.isInteger(month) ||
    !Number.isInteger(year) ||
    !Number.isInteger(hour) ||
    !Number.isInteger(minute) ||
    day < 1 ||
    month < 1 ||
    month > 12 ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return null;
  }

  const date = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day ||
    date.getUTCHours() !== hour ||
    date.getUTCMinutes() !== minute
  ) {
    return null;
  }

  return {
    serial: (date.getTime() - Date.UTC(1899, 11, 30)) / 86400000,
    text: `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year} ${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
  };
}

function extractFirstDateTime(text) {
  const dateTimePattern =
    /(\d{1,2}\s*[\/.-]\s*\d{1,2}\s*[\/.-]\s*\d{2,4})\s*(?:[-–—|,;]\s*)?(\d{1,2})\s*[:.]\s*(\d{2})(?:\s*[:.]\s*(\d{2}))?/g;

  for (const match of text.matchAll(dateTimePattern)) {
    const parsed = parseExcelDateTime(
      match[1].replace(/\s+/g, ""),
      match[2],
      match[3],
      match[4] || "0",
    );
    if (parsed) return parsed;
  }

  return null;
}

async function graph(path, options = {}) {
  const response = await connectors.proxy("onedrive", path, options);
  let body = null;

  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const providerMessage =
      body?.error?.message || `Microsoft Graph respondió HTTP ${response.status}.`;
    throw new Error(providerMessage);
  }

  return body;
}

async function findWorkbook() {
  const body = await graph(
    "/v1.0/me/drive/root/search(q='Calculadora%20de%20RAID')?$top=50",
  );
  const files = (body.value || []).filter((item) => item.file);

  const exact = files.find(
    (item) => normalize(item.name) === normalize(WORKBOOK_NAME),
  );
  if (exact) return exact;

  for (const workbookPath of WORKBOOK_PATHS) {
    try {
      const item = await graph(
        `/v1.0/me/drive/root:/${encodeURIComponent(workbookPath).replaceAll("%2F", "/")}`,
      );
      if (item?.file && normalize(item.name) === normalize(WORKBOOK_NAME)) {
        return item;
      }
    } catch {
      // Try the next configured path.
    }
  }

  throw new Error(
    "No encontré el libro RAID. Revisa ONEDRIVE_WORKBOOK_PATH y que el archivo esté compartido con la cuenta conectada.",
  );
}

async function findWorksheetAndMatch(workbook, ocrText) {
  const worksheetsBody = await graph(
    `/v1.0/me/drive/items/${encodeURIComponent(workbook.id)}/workbook/worksheets?$select=id,name`,
  );
  const worksheet = (worksheetsBody.value || []).find(
    (item) => normalize(item.name) === REQUIRED_WORKSHEET,
  );
  if (!worksheet) {
    throw new Error("No encontré la pestaña obligatoria CALCULADORA.");
  }

  const range = await graph(
    `/v1.0/me/drive/items/${encodeURIComponent(workbook.id)}/workbook/worksheets/${encodeURIComponent(worksheet.id)}/usedRange(valuesOnly=true)`,
  );
  const values = range.values || [];
  let headerRowIndex = -1;

  for (let rowIndex = 0; rowIndex < values.length; rowIndex += 1) {
    const row = values[rowIndex] || [];
    const normalizedRow = row.map(normalize);
    if (
      normalizedRow[0] === RAID_HEADER &&
      normalizedRow[1] === CURRENT_DATE_HEADER
    ) {
      headerRowIndex = rowIndex;
      break;
    }
  }

  if (headerRowIndex === -1) {
    throw new Error(
      "La hoja CALCULADORA no tiene RAID en A y FECHA HORA ACTUAL en B.",
    );
  }

  const lines = String(ocrText || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const bossRows = [];

  for (
    let rowIndex = headerRowIndex + 1;
    rowIndex < values.length;
    rowIndex += 1
  ) {
    const boss = String(values[rowIndex]?.[0] ?? "").trim();
    if (normalize(boss).length < 3) continue;

    const lineIndex = lines.findIndex((line) => lineContainsBoss(line, boss));
    if (lineIndex !== -1) {
      bossRows.push({ boss, rowIndex, lineIndex });
    }
  }

  if (!bossRows.length) {
    throw new Error(
      "El OCR no contiene ningún jefe de la columna A (RAID) de CALCULADORA.",
    );
  }

  bossRows.sort((a, b) => a.lineIndex - b.lineIndex);
  const matchesByRow = new Map();

  for (let index = 0; index < bossRows.length; index += 1) {
    const current = bossRows[index];
    const nextLineIndex = bossRows[index + 1]?.lineIndex ?? lines.length;
    const block = lines.slice(current.lineIndex, nextLineIndex).join("\n");
    const dateTime = extractFirstDateTime(block);

    // Un jefe sin fecha/hora válida queda intacto en Excel.
    if (!dateTime) continue;

    const previous = matchesByRow.get(current.rowIndex);
    if (previous && previous.dateTime.text !== dateTime.text) {
      throw new Error(
        `El OCR contiene fechas distintas para el jefe ${current.boss}.`,
      );
    }

    matchesByRow.set(current.rowIndex, {
      boss: current.boss,
      rowIndex: current.rowIndex,
      dateTime,
    });
  }

  const matches = [...matchesByRow.values()];
  if (!matches.length) {
    throw new Error(
      "Encontré jefes, pero ninguna fecha/hora válida asociada en el OCR.",
    );
  }

  return {
    worksheet,
    matches,
    headerRowIndex,
    range,
  };
}

async function updateWorkbook(ocrText, dryRun = false) {
  const workbook = await findWorkbook();
  const found = await findWorksheetAndMatch(workbook, ocrText);
  const firstRow = usedRangeStartRow(found.range.address);
  const updates = [];

  for (const match of found.matches) {
    const excelRow = firstRow + match.rowIndex;
    const cellAddress = `B${excelRow}`;

    if (!dryRun) {
      await graph(
        `/v1.0/me/drive/items/${encodeURIComponent(workbook.id)}/workbook/worksheets/${encodeURIComponent(found.worksheet.id)}/range(address='${cellAddress}')`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ values: [[match.dateTime.serial]] }),
        },
      );
    }

    updates.push({
      boss: match.boss,
      cell: cellAddress,
      sourceDateTime: match.dateTime.text,
    });
  }

  return {
    workbook: workbook.name,
    worksheet: found.worksheet.name,
    updates,
    dryRun,
  };
}

async function main() {
  const input = JSON.parse(await readStdin());
  const result = await updateWorkbook(input.ocrText, Boolean(input.dryRun));
  process.stdout.write(JSON.stringify({ ok: true, ...result }));
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

main().catch((error) => {
  process.stdout.write(
    JSON.stringify({ ok: false, error: error.message || "Error desconocido." }),
  );
  process.exitCode = 1;
});
