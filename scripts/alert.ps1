# WiWave local alert: shows a Windows toast notification.
# Opt-in only, triggered by the WiWave server when a sustained signal change starts.
param(
    [string]$Title = 'WiWave',
    [string]$Body = 'Signal change detected.'
)
$ErrorActionPreference = 'Stop'
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $template = @"
<toast><visual><binding template="ToastGeneric"><text>$([System.Net.WebUtility]::HtmlEncode($Title))</text><text>$([System.Net.WebUtility]::HtmlEncode($Body))</text></binding></visual></toast>
"@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
} catch {
    # Toast support varies across Windows builds; a failure must never break sensing.
    exit 0
}
