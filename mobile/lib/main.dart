import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'l10n/app_localizations.dart';
import 'locale_manager.dart';
import 'screens/conversation_screen.dart';
import 'screens/pairing_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterForegroundTask.init(
    androidNotificationOptions: AndroidNotificationOptions(
      channelId: 'mirach_fg',
      channelName: 'Mirach',
      onlyAlertOnce: true,
    ),
    iosNotificationOptions: const IOSNotificationOptions(
      showNotification: false,
    ),
    foregroundTaskOptions: ForegroundTaskOptions(
      eventAction: ForegroundTaskEventAction.nothing(),
      autoRunOnBoot: false,
      allowWakeLock: true,
    ),
  );
  // Read persisted language before runApp to avoid a locale flash on startup.
  await initLocale();
  runApp(const MirachApp());
}

class MirachApp extends StatelessWidget {
  const MirachApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Locale>(
      valueListenable: localeNotifier,
      builder: (context, locale, _) => MaterialApp(
        title: 'Mirach',
        debugShowCheckedModeBanner: false,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: locale,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF4caf50),
            brightness: Brightness.dark,
          ),
          scaffoldBackgroundColor: const Color(0xFF0f0f0f),
          appBarTheme: const AppBarTheme(
            backgroundColor: Color(0xFF1a1a1a),
            foregroundColor: Color(0xFFe0e0e0),
            elevation: 0,
          ),
        ),
        home: const _StartupRouter(),
      ),
    );
  }
}

/// Reads stored credentials and routes to PairingScreen or ConversationScreen.
class _StartupRouter extends StatefulWidget {
  const _StartupRouter();

  @override
  State<_StartupRouter> createState() => _StartupRouterState();
}

class _StartupRouterState extends State<_StartupRouter> {
  static const _s = FlutterSecureStorage();

  @override
  void initState() {
    super.initState();
    _route();
  }

  Future<void> _route() async {
    final baseUrl = await _s.read(key: 'mirach_base_url');
    final token = await _s.read(key: 'mirach_token');
    if (!mounted) return;
    if (baseUrl != null && token != null) {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => ConversationScreen(baseUrl: baseUrl, token: token),
        ),
      );
    } else {
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const PairingScreen()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0f0f0f),
      body: Center(
        child: CircularProgressIndicator(color: Color(0xFF4caf50)),
      ),
    );
  }
}
