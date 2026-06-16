import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final localeNotifier = ValueNotifier<Locale>(const Locale('en'));

Future<void> initLocale() async {
  const storage = FlutterSecureStorage();
  final code = await storage.read(key: 'mirach_lang') ?? 'en';
  localeNotifier.value = Locale(code);
}

Future<void> setLocale(Locale locale) async {
  localeNotifier.value = locale;
  const storage = FlutterSecureStorage();
  await storage.write(key: 'mirach_lang', value: locale.languageCode);
}

class LangSelector extends StatelessWidget {
  const LangSelector({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Locale>(
      valueListenable: localeNotifier,
      builder: (context, locale, _) => Theme(
        data: ThemeData.dark(useMaterial3: true).copyWith(
          colorScheme: const ColorScheme.dark(
            primary: Color(0xFF4caf50),
            onPrimary: Colors.white,
            secondaryContainer: Color(0xFF1e3a1e),
            onSecondaryContainer: Color(0xFF4caf50),
            surface: Color(0xFF252525),
            onSurface: Color(0xFF999999),
            outline: Color(0xFF383838),
          ),
        ),
        child: SegmentedButton<Locale>(
          segments: const [
            ButtonSegment(
              value: Locale('en'),
              label: Text('EN', style: TextStyle(fontSize: 12)),
            ),
            ButtonSegment(
              value: Locale('es'),
              label: Text('ES', style: TextStyle(fontSize: 12)),
            ),
          ],
          selected: {locale},
          onSelectionChanged: (s) => setLocale(s.first),
          showSelectedIcon: false,
        ),
      ),
    );
  }
}
