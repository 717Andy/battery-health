using BatteryHealth.Core.Domain;
using LiveChartsCore;
using LiveChartsCore.Defaults;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Painting;
using SkiaSharp;

namespace BatteryHealth.App.Charts;

/// <summary>
/// LiveCharts2 helpers. OxyPlot.Windows targets UWP / WinUI 2 and does not
/// officially support WinUI 3, so the desktop app uses LiveChartsCore.
/// </summary>
public static class ChartFactory
{
    private static readonly SolidColorPaint Teal = new(SKColor.Parse("#0F766E"));
    private static readonly SolidColorPaint Amber = new(SKColor.Parse("#D97706"));
    private static readonly SolidColorPaint Rose = new(SKColor.Parse("#BE123C"));
    private static readonly SolidColorPaint Slate = new(SKColor.Parse("#64748B"));

    public static ISeries[] SensorSeries(BatteryCycle? cycle)
    {
        if (cycle is null || !cycle.HasTrace)
        {
            return [];
        }

        return
        [
            Line("Voltage (V)", cycle.TimeS, cycle.VoltageV, Teal),
            Line("Current (A)", cycle.TimeS, cycle.CurrentA, Amber),
            Line("Temperature (°C)", cycle.TimeS, cycle.TemperatureC, Rose),
        ];
    }

    public static ISeries[] FadeSeries(BatteryRecord? battery, IReadOnlyList<FadePoint>? stressed = null)
    {
        if (battery is null)
        {
            return [];
        }

        var baseline = battery.DischargeCycles
            .Where(c => c.CapacityAh.HasValue)
            .Select(c => new ObservablePoint(c.CycleIndex, c.CapacityAh))
            .ToArray();

        var series = new List<ISeries>
        {
            new LineSeries<ObservablePoint>
            {
                Name = "Measured capacity",
                Values = baseline,
                Fill = null,
                Stroke = Teal,
                GeometrySize = 0,
                LineSmoothness = 0.15,
            },
        };

        if (stressed is { Count: > 0 })
        {
            series.Add(new LineSeries<ObservablePoint>
            {
                Name = "Stressed capacity",
                Values = stressed.Select(p => new ObservablePoint(p.CycleIndex, p.CapacityAh)).ToArray(),
                Fill = null,
                Stroke = Rose,
                GeometrySize = 0,
                LineSmoothness = 0.15,
            });
        }

        return series.ToArray();
    }

    public static ISeries[] SohSeries(IReadOnlyList<ForecastResult> forecasts, BatteryRecord battery)
    {
        var predicted = forecasts.Select(f => new ObservablePoint(f.CycleIndex, f.PredictedSoh * 100)).ToArray();
        var observed = forecasts
            .Where(f => f.ObservedSoh.HasValue)
            .Select(f => new ObservablePoint(f.CycleIndex, f.ObservedSoh!.Value * 100))
            .ToArray();
        return
        [
            new LineSeries<ObservablePoint>
            {
                Name = "Predicted SoH %",
                Values = predicted,
                Fill = null,
                Stroke = Teal,
                GeometrySize = 0,
            },
            new LineSeries<ObservablePoint>
            {
                Name = "Measured SoH %",
                Values = observed,
                Fill = null,
                Stroke = Slate,
                GeometrySize = 0,
                StrokeDashArray = [4, 3],
            },
        ];
    }

    public static Axis[] TimeAxis() => [new Axis { Name = "Time (s)" }];
    public static Axis[] CycleAxis() => [new Axis { Name = "Cycle" }];
    public static Axis[] SensorYAxis() => [new Axis { Name = "V / A / °C" }];
    public static Axis[] CapacityAxis() => [new Axis { Name = "Capacity (Ah)" }];
    public static Axis[] SohAxis() => [new Axis { Name = "SoH (%)" }];

    private static LineSeries<ObservablePoint> Line(string name, IReadOnlyList<double> x, IReadOnlyList<double> y, SolidColorPaint paint)
    {
        var n = Math.Min(x.Count, y.Count);
        var points = new ObservablePoint[n];
        for (var i = 0; i < n; i++)
        {
            points[i] = new ObservablePoint(x[i], y[i]);
        }

        return new LineSeries<ObservablePoint>
        {
            Name = name,
            Values = points,
            Fill = null,
            Stroke = paint,
            GeometrySize = 0,
            LineSmoothness = 0.2,
        };
    }
}
