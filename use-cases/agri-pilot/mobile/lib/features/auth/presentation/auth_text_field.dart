import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class AuthTextField extends StatefulWidget {
  const AuthTextField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.prefixIcon,
    this.keyboardType,
    this.obscureText = false,
    this.showVisibilityToggle = false,
    this.helperText,
    this.inputFormatters,
    this.textInputAction,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final IconData? prefixIcon;
  final TextInputType? keyboardType;
  final bool obscureText;
  final bool showVisibilityToggle;
  final String? helperText;
  final List<TextInputFormatter>? inputFormatters;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onSubmitted;

  factory AuthTextField.phone({
    required TextEditingController controller,
    TextInputAction? textInputAction,
    ValueChanged<String>? onSubmitted,
  }) {
    return AuthTextField(
      controller: controller,
      label: 'Phone number',
      prefixIcon: Icons.phone_outlined,
      keyboardType: TextInputType.phone,
      textInputAction: textInputAction,
      onSubmitted: onSubmitted,
      inputFormatters: [
        FilteringTextInputFormatter.allow(RegExp(r'[\d\s\+\-\(\)]')),
      ],
    );
  }

  factory AuthTextField.password({
    required TextEditingController controller,
    required String label,
    String? helperText,
    TextInputAction? textInputAction,
    ValueChanged<String>? onSubmitted,
  }) {
    return AuthTextField(
      controller: controller,
      label: label,
      prefixIcon: Icons.lock_outline,
      obscureText: true,
      showVisibilityToggle: true,
      helperText: helperText,
      textInputAction: textInputAction,
      onSubmitted: onSubmitted,
    );
  }

  @override
  State<AuthTextField> createState() => _AuthTextFieldState();
}

class _AuthTextFieldState extends State<AuthTextField> {
  late bool _obscure;

  @override
  void initState() {
    super.initState();
    _obscure = widget.obscureText;
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: TextFormField(
        controller: widget.controller,
        decoration: InputDecoration(
          labelText: widget.label,
          hintText: widget.hint,
          helperText: widget.helperText,
          prefixIcon: widget.prefixIcon != null ? Icon(widget.prefixIcon) : null,
          suffixIcon: widget.showVisibilityToggle
              ? IconButton(
                  icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                  onPressed: () => setState(() => _obscure = !_obscure),
                )
              : null,
          border: const OutlineInputBorder(),
        ),
        keyboardType: widget.keyboardType,
        obscureText: _obscure,
        inputFormatters: widget.inputFormatters,
        textInputAction: widget.textInputAction,
        onFieldSubmitted: widget.onSubmitted,
      ),
    );
  }
}
