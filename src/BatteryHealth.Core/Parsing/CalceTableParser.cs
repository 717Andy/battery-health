using System.Data;
using System.Globalization;
using System.Text;
using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Features;
using ExcelDataReader;

namespace BatteryHealth.Core.Parsing;

/// <summary>
/// CALCE / Arbin CSV and Excel cycle logs (Cycle_Index, Voltage, Current, capacities).
/// </summary>
public static class CalceTableParser
{
    private static readonly Dictionary<string, string[]> Aliases = new()
    {
        ["cycle_index"] = ["cycle_index", "cycleindex", "cycle", "cycle_number", "cyc"],
        ["voltage"] = ["voltage_v", "voltagev", "voltage", "volt", "v"],
        ["current"] = ["current_a", "currenta", "current", "curr", "i"],
        ["time"] = ["test_times", "test_time_s", "testtime", "step_times", "step_time_s", "time_s", "time", "t"],
        ["discharge_capacity"] = ["discharge_capacity_ah", "dischargecapacityah", "discharge_capacity", "capacity_ah", "capacity", "q_discharge"],
        ["temperature"] = ["temperature_c", "temperaturec", "temperature_c_1", "temperature", "temp"],
    };

    public static BatteryRecord ParseFile(string path, string? batteryId = null, double ratedCapacityAh = 1.1, double ambientTempC = 25.0)
    {
        var ext = Path.GetExtension(path).ToLowerInvariant();
        if (ext is ".xlsx" or ".xls")
        {
            return ParseExcel(path, batteryId, ratedCapacityAh, ambientTempC);
        }

        using var reader = new StreamReader(path);
        return ParseCsv(reader, batteryId ?? Path.GetFileNameWithoutExtension(path), ratedCapacityAh, ambientTempC);
    }

    public static BatteryRecord ParseCsv(TextReader reader, string batteryId, double ratedCapacityAh = 1.1, double ambientTempC = 25.0)
    {
        var header = reader.ReadLine() ?? throw new InvalidDataException("CALCE CSV is empty");
        var columns = SplitCsv(header);
        var map = Resolve(columns);
        if (!map.ContainsKey("voltage") || !map.ContainsKey("current"))
        {
            throw new InvalidDataException("CALCE table needs Voltage and Current columns");
        }

        var rows = new List<string[]>();
        while (reader.ReadLine() is { } line)
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            rows.Add(SplitCsv(line));
        }

        return Build(rows, columns, map, batteryId, ratedCapacityAh, ambientTempC, "calce");
    }

    public static BatteryRecord ParseExcel(string path, string? batteryId, double ratedCapacityAh, double ambientTempC)
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        using var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        using var reader = ExcelReaderFactory.CreateReader(stream);
        var data = reader.AsDataSet();
        if (data.Tables.Count == 0 || data.Tables[0].Rows.Count < 2)
        {
            throw new InvalidDataException("Excel workbook has no data");
        }

        var table = data.Tables[0];
        var columns = table.Rows[0].ItemArray.Select(v => Convert.ToString(v, CultureInfo.InvariantCulture) ?? "").ToArray();
        var map = Resolve(columns);
        var rows = new List<string[]>();
        for (var r = 1; r < table.Rows.Count; r++)
        {
            rows.Add(table.Rows[r].ItemArray.Select(v => Convert.ToString(v, CultureInfo.InvariantCulture) ?? "").ToArray());
        }

        return Build(rows, columns, map, batteryId ?? Path.GetFileNameWithoutExtension(path), ratedCapacityAh, ambientTempC, "calce");
    }

    private static BatteryRecord Build(
        List<string[]> rows,
        string[] columns,
        Dictionary<string, int> map,
        string batteryId,
        double ratedCapacityAh,
        double ambientTempC,
        string source)
    {
        double Num(string[] row, string key)
        {
            if (!map.TryGetValue(key, out var idx) || idx >= row.Length)
            {
                return double.NaN;
            }

            return double.TryParse(row[idx], NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : double.NaN;
        }

        var grouped = new Dictionary<int, List<string[]>>();
        foreach (var row in rows)
        {
            var cycle = map.ContainsKey("cycle_index") ? (int)Math.Round(Num(row, "cycle_index")) : 1;
            if (!grouped.TryGetValue(cycle, out var list))
            {
                list = [];
                grouped[cycle] = list;
            }

            list.Add(row);
        }

        var record = new BatteryRecord
        {
            BatteryId = batteryId,
            Source = source,
            RatedCapacityAh = ratedCapacityAh,
            RatedCapacityAssumed = true,
            EolCapacityFraction = 0.70,
            Chemistry = "Li-ion (CALCE)",
            AmbientTemperatureC = ambientTempC,
        };

        var ordinal = 0;
        foreach (var cycleId in grouped.Keys.OrderBy(k => k))
        {
            var pack = grouped[cycleId];
            var voltage = pack.Select(r => Num(r, "voltage")).ToList();
            var current = pack.Select(r => Num(r, "current")).ToList();
            var time = map.ContainsKey("time")
                ? pack.Select(r => Num(r, "time")).ToList()
                : Enumerable.Range(0, pack.Count).Select(i => (double)i).ToList();
            var temp = map.ContainsKey("temperature")
                ? pack.Select(r => Num(r, "temperature")).ToList()
                : Enumerable.Repeat(ambientTempC, pack.Count).ToList();

            var discharge = new List<int>();
            for (var i = 0; i < current.Count; i++)
            {
                if (current[i] < -0.02)
                {
                    discharge.Add(i);
                }
            }

            if (discharge.Count < 5)
            {
                for (var i = 0; i < current.Count; i++)
                {
                    if (Math.Abs(current[i]) > 0.02 && voltage[i] < 4.15)
                    {
                        discharge.Add(i);
                    }
                }
            }

            if (discharge.Count < 5)
            {
                continue;
            }

            var t = discharge.Select(i => time[i]).ToList();
            var v = discharge.Select(i => voltage[i]).ToList();
            var cur = discharge.Select(i => current[i]).ToList();
            var te = discharge.Select(i => temp[i]).ToList();
            var t0 = t[0];
            t = t.Select(x => x - t0).ToList();

            double capacity;
            if (map.ContainsKey("discharge_capacity"))
            {
                var caps = discharge.Select(i => Num(pack[i], "discharge_capacity")).Where(double.IsFinite).ToList();
                capacity = caps.Count > 0 ? caps.Max() : IntegrateCapacity(cur, t);
            }
            else
            {
                capacity = IntegrateCapacity(cur, t);
            }

            ordinal++;
            var soh = ratedCapacityAh > 0 ? capacity / ratedCapacityAh : (double?)null;
            var features = CycleFeatureExtractor.Extract(ordinal, t, v, cur, te, ambientTempC, soh);
            record.Cycles.Add(new BatteryCycle
            {
                CycleIndex = ordinal,
                Type = "discharge",
                AmbientTemperatureC = ambientTempC,
                CapacityAh = capacity,
                TimeS = t,
                VoltageV = v,
                CurrentA = cur,
                TemperatureC = te,
                Features = features,
            });
        }

        if (record.Cycles.Count == 0)
        {
            throw new InvalidDataException("No discharge cycles found in CALCE table");
        }

        _ = columns;
        return record;
    }

    private static double IntegrateCapacity(IReadOnlyList<double> current, IReadOnlyList<double> time)
    {
        var s = 0.0;
        for (var i = 1; i < current.Count; i++)
        {
            s += 0.5 * (Math.Abs(current[i]) + Math.Abs(current[i - 1])) * (time[i] - time[i - 1]);
        }

        return s / 3600.0;
    }

    private static Dictionary<string, int> Resolve(IReadOnlyList<string> columns)
    {
        var normalized = new Dictionary<string, int>(StringComparer.Ordinal);
        for (var i = 0; i < columns.Count; i++)
        {
            normalized[Normalize(columns[i])] = i;
        }

        var map = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var (key, aliases) in Aliases)
        {
            foreach (var alias in aliases)
            {
                if (normalized.TryGetValue(alias, out var idx))
                {
                    map[key] = idx;
                    break;
                }
            }
        }

        return map;
    }

    private static string Normalize(string name) =>
        new string(name.ToLowerInvariant().Where(ch => char.IsLetterOrDigit(ch) || ch == '_').ToArray())
            .Replace("(", "", StringComparison.Ordinal)
            .Replace(")", "", StringComparison.Ordinal);

    private static string[] SplitCsv(string line)
    {
        var result = new List<string>();
        var cur = new StringBuilder();
        var quoted = false;
        foreach (var ch in line)
        {
            if (ch == '"')
            {
                quoted = !quoted;
                continue;
            }

            if (ch == ',' && !quoted)
            {
                result.Add(cur.ToString());
                cur.Clear();
                continue;
            }

            cur.Append(ch);
        }

        result.Add(cur.ToString());
        return result.ToArray();
    }
}
