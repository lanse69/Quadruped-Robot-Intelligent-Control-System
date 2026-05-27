// 配置加载通用实现

#include "qrics/config/config_error.hpp"

#include <fstream>
#include <string>
#include <utility>
#include <optional>
#include <string_view>

namespace qrics::config {

namespace {

struct KeyValue final {
  std::string key{};
  std::string value{};
};

[[nodiscard]] std::string trim(const std::string& value) {
  const auto first = value.find_first_not_of(" \t\r\n");
  if (first == std::string::npos) {
    return {};
  }
  const auto last = value.find_last_not_of(" \t\r\n");
  return value.substr(first, last - first + 1U);
}

[[nodiscard]] std::string strip_comment(const std::string& line) {
  const auto marker = line.find('#');
  if (marker == std::string::npos) {
    return line;
  }
  return line.substr(0U, marker);
}

[[nodiscard]] std::string unquote(const std::string& value) {
  if (value.size() < 2U) {
    return value;
  }

  const char first = value.front();
  const char last = value.back();

  if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
    return value.substr(1U, value.size() - 2U);
  }

  return value;
}

[[nodiscard]] bool starts_with(std::string_view value, std::string_view prefix) {
  return value.starts_with(prefix);
}

[[nodiscard]] std::optional<KeyValue> split_key_value(const std::string& line) {
  const auto separator = line.find(':');
  if (separator == std::string::npos) {
    return std::nullopt;
  }

  KeyValue result{};
  result.key = trim(line.substr(0U, separator));
  result.value = unquote(trim(line.substr(separator + 1U)));

  if (result.key.empty()) {
    return std::nullopt;
  }

  return result;
}

[[nodiscard]] std::string make_list_key(const std::string& list_section, int list_index,
                                        const std::string& key) {
  const auto index_text = std::to_string(list_index);

  std::string result{};
  result.reserve(list_section.size() + index_text.size() + key.size() + 3U);
  result.append(list_section);
  result.push_back('[');
  result.append(index_text);
  result.append("].");
  result.append(key);

  return result;
}

[[nodiscard]] std::string make_section_key(const std::string& section, const std::string& key) {
  std::string result{};
  result.reserve(section.size() + key.size() + 1U);
  result.append(section);
  result.push_back('.');
  result.append(key);
  return result;
}

void put_value(FlatYamlDocument& document, const std::string& section, const std::string& key,
               const std::string& value) {
  if (section.empty()) {
    document.values[key] = value;
    return;
  }
  document.values[make_section_key(section, key)] = value;
}

}  // namespace

qrics::common::Error make_config_error(const std::string& code, const std::string& message) {
  return qrics::common::Error{code, message};
}

qrics::common::Result<FlatYamlDocument> load_flat_yaml_file(const std::string& path) {
  std::ifstream input{path};
  if (!input.is_open()) {
    return qrics::common::Result<FlatYamlDocument>::failure(
        {make_config_error("CONFIG_FILE_OPEN_FAILED", "Cannot open config file: " + path)});
  }

  FlatYamlDocument document{};
  std::string section{};
  std::string list_section{};
  int list_index{-1};
  std::string line{};
  int line_number{0};

  while (std::getline(input, line)) {
    ++line_number;
    const auto clean_line = strip_comment(line);
    const auto trimmed = trim(clean_line);
    if (trimmed.empty()) {
      continue;
    }

    if (!starts_with(clean_line, " ") && trimmed.ends_with(':')) {
      section = trimmed.substr(0U, trimmed.size() - 1U);
      list_section.clear();
      list_index = -1;
      continue;
    }

    if (starts_with(clean_line, "  - ")) {
      list_section = section;
      ++list_index;
      const auto entry = split_key_value(trim(clean_line.substr(4U)));
      if (!entry.has_value()) {
        return qrics::common::Result<FlatYamlDocument>::failure(
            {make_config_error("CONFIG_PARSE_FAILED",
                               "Unsupported list item at line " + std::to_string(line_number))});
      }
      document.values[make_list_key(list_section, list_index, entry->key)] = entry->value;
      continue;
    }

    if (starts_with(clean_line, "    ") && !list_section.empty() && list_index >= 0) {
      const auto entry = split_key_value(trim(clean_line));
      if (!entry.has_value()) {
        return qrics::common::Result<FlatYamlDocument>::failure(
            {make_config_error("CONFIG_PARSE_FAILED", "Unsupported list property at line " +
                                                          std::to_string(line_number))});
      }
      document.values[make_list_key(list_section, list_index, entry->key)] = entry->value;
      continue;
    }

    if (starts_with(clean_line, "  ")) {
      const auto entry = split_key_value(trimmed);
      if (!entry.has_value()) {
        return qrics::common::Result<FlatYamlDocument>::failure(
            {make_config_error("CONFIG_PARSE_FAILED", "Unsupported key-value line at line " +
                                                          std::to_string(line_number))});
      }
      put_value(document, section, entry->key, entry->value);
      continue;
    }

    return qrics::common::Result<FlatYamlDocument>::failure({make_config_error(
        "CONFIG_PARSE_FAILED", "Unsupported YAML line at line " + std::to_string(line_number))});
  }

  return qrics::common::Result<FlatYamlDocument>::success(std::move(document));
}

}  // namespace qrics::config
