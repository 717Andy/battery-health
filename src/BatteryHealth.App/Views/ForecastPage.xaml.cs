using BatteryHealth.App.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;

namespace BatteryHealth.App.Views;

public sealed partial class ForecastPage : Page
{
    public ForecastViewModel ViewModel { get; } = new(App.Workspace);

    public ForecastPage()
    {
        InitializeComponent();
        ViewModel.Refresh();
    }

    private void OnRefresh(object sender, RoutedEventArgs e) => ViewModel.Refresh();

    private async void OnLoadDemo(object sender, RoutedEventArgs e)
    {
        await App.Workspace.LoadFromPath(WorkspaceViewModel.DemoPath);
        ViewModel.Refresh();
    }

    private async void OnExport(object sender, RoutedEventArgs e)
    {
        var picker = new FileSavePicker();
        picker.FileTypeChoices.Add("CSV and JSON", new List<string> { ".csv" });
        picker.SuggestedFileName = "battery-decision";
        if (App.MainWindow is not null)
        {
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindow);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);
        }

        var file = await picker.PickSaveFileAsync();
        if (file is not null)
        {
            ViewModel.ExportTo(file.Path);
        }
    }
}
