using System.Text.Json;
using BatteryHealth.Core.Domain;

namespace BatteryHealth.Core.Parsing;

public static class CanonicalJsonParser
{
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
    };

    public static BatteryRecord ParseFile(string path)
    {
        using var stream = File.OpenRead(path);
        return Parse(stream);
    }

    public static BatteryRecord Parse(Stream stream)
    {
        var record = JsonSerializer.Deserialize<BatteryRecord>(stream, Options)
                     ?? throw new InvalidDataException("Battery JSON deserialized to null");
        if (string.IsNullOrWhiteSpace(record.BatteryId))
        {
            throw new InvalidDataException("Battery JSON is missing batteryId");
        }

        return record;
    }

    public static BatteryRecord Parse(string json)
    {
        var record = JsonSerializer.Deserialize<BatteryRecord>(json, Options)
                     ?? throw new InvalidDataException("Battery JSON deserialized to null");
        return record;
    }
}
