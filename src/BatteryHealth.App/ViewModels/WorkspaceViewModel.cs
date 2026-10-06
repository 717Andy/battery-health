using BatteryHealth.Core.Domain;
using BatteryHealth.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace BatteryHealth.App.ViewModels;

/// <summary>Shared session for the three Fluent pages.</summary>
public partial class WorkspaceViewModel : ObservableObject
{
    private BatteryAnalyticsService? _service;

    [ObservableProperty] private BatteryRecord? battery;
    [ObservableProperty] private BatteryCycle? selectedCycle;
    [ObservableProperty] private ForecastResult? forecast;
    [ObservableProperty] private string status = "Load a NASA processed JSON or a CALCE CSV/Excel log.";
    [ObservableProperty] private string? errorMessage;
    [ObservableProperty] private bool isBusy;
    [ObservableProperty] private string batteryTitle = "No battery loaded";
    [ObservableProperty] private string summaryLine = "Fleet diagnostic — local ONNX, no cloud.";

    public IReadOnlyList<BatteryCycle> DischargeCycles =>
        Battery?.DischargeCycles.ToList() ?? [];

    public BatteryAnalyticsService Service => _service ??= new BatteryAnalyticsService();

    public event EventHandler? BatteryChanged;
    public event EventHandler? CycleChanged;

    [RelayCommand]
    public void LoadFromPath(string path)
    {
        try
        {
            IsBusy = true;
            ErrorMessage = null;
            var record = Service.Load(path);
            Battery = record;
            SelectedCycle = record.DischargeCycles.LastOrDefault(c => c.HasTrace)
                            ?? record.DischargeCycles.LastOrDefault();
            BatteryTitle = $"{record.BatteryId} · {record.Source.ToUpperInvariant()}";
            var discharges = record.DischargeCycles.ToList();
            var first = discharges.FirstOrDefault()?.CapacityAh;
            var last = discharges.LastOrDefault()?.CapacityAh;
            SummaryLine =
                $"{discharges.Count} discharge cycles · rated {record.RatedCapacityAh:0.00} Ah · " +
                $"EOL {record.EolCapacityFraction:P0} ({record.EolCapacityAh:0.00} Ah) · " +
                $"capacity {first:0.000} → {last:0.000} Ah";
            Status = $"Loaded {path}";
            RefreshForecast();
            OnPropertyChanged(nameof(DischargeCycles));
            BatteryChanged?.Invoke(this, EventArgs.Empty);
            CycleChanged?.Invoke(this, EventArgs.Empty);
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
            Status = "Could not load file.";
        }
        finally
        {
            IsBusy = false;
        }
    }

    public void SelectCycle(int cycleIndex)
    {
        if (Battery is null)
        {
            return;
        }

        SelectedCycle = Battery.CycleAt(cycleIndex);
        RefreshForecast();
        CycleChanged?.Invoke(this, EventArgs.Empty);
    }

    public void RefreshForecast()
    {
        if (Battery is null || SelectedCycle is null)
        {
            Forecast = null;
            return;
        }

        try
        {
            Forecast = Service.Forecast(Battery, SelectedCycle.CycleIndex);
        }
        catch (Exception ex)
        {
            ErrorMessage = ex.Message;
        }
    }

    partial void OnSelectedCycleChanged(BatteryCycle? value)
    {
        if (value is not null)
        {
            RefreshForecast();
            CycleChanged?.Invoke(this, EventArgs.Empty);
        }
    }
}
