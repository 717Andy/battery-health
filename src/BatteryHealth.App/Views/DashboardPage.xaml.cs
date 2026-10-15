using BatteryHealth.App.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;

namespace BatteryHealth.App.Views;

public sealed partial class DashboardPage : Page
{
    public DashboardViewModel ViewModel { get; } = new(App.Workspace);

    public DashboardPage()
    {
        InitializeComponent();
        ViewModel.Refresh();
    }

    private async void OnOpenFile(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker();
        picker.FileTypeFilter.Add(".json");
        picker.FileTypeFilter.Add(".csv");
        picker.FileTypeFilter.Add(".xlsx");
        picker.FileTypeFilter.Add(".xls");
        if (App.MainWindow is not null)
        {
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindow);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);
        }

        var file = await picker.PickSingleFileAsync();
        if (file is not null)
        {
            await ViewModel.Workspace.LoadFromPath(file.Path);
            ViewModel.Refresh();
        }
    }

    private async void OnLoadDemo(object sender, RoutedEventArgs e)
    {
        await ViewModel.Workspace.LoadFromPath(WorkspaceViewModel.DemoPath);
        ViewModel.Refresh();
    }
}
