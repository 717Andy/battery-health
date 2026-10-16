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
        using var doc = JsonDocument.Parse(stream);
        return FromDocument(doc);
    }

    public static BatteryRecord Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return FromDocument(doc);
    }

    private static BatteryRecord FromDocument(JsonDocument doc)
    {
        var root = doc.RootElement;
        var record = JsonSerializer.Deserialize<BatteryRecord>(root.GetRawText(), Options)
                     ?? throw new InvalidDataException("Battery JSON deserialized to null");
        if (string.IsNullOrWhiteSpace(record.BatteryId))
        {
            throw new InvalidDataException("Battery JSON is missing batteryId");
        }

        record.RatedCapacityAssumed = !HasProperty(root, "ratedCapacityAh");
        return record;
    }

    private static bool HasProperty(JsonElement root, string name)
    {
        foreach (var property in root.EnumerateObject())
        {
            if (string.Equals(property.Name, name, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }
}
