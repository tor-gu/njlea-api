#!/usr/bin/env Rscript
# Export the njlea tables to CSV, the input of scripts/build_data.py, and R's own
# results for the parity test.
#
# Usage: Rscript scripts/export_data.R <git-ref> [out-dir] [expected-dir]
#
# Installs tor-gu/njlea at <git-ref> (e.g. v0.1.0) into a temporary library,
# with its njmunicipalities dependency, and writes to out-dir (default: data):
#   <table>.csv         the five njlea tables, in R's row order (NA is an empty
#                       field; empty strings are exported as NA, and reported)
#   municipalities.csv  njmunicipalities' internal municipalities table, which
#                       get_agency_municipalities() joins through
#   columns.csv         table, position, column, type (integer, date, factor or
#                       character)
#   levels.csv          table, column, position, level (every factor column)
#   SOURCE              the njlea and njmunicipalities releases, and the years
# and to expected-dir (default: tests/parity/expected), gzipped:
#   agencies.csv.gz                 get_agencies(y), y = MIN_YEAR..MAX_YEAR,
#                                   with a year column
#   agency_municipalities.csv.gz    get_agency_municipalities(y, gy), y =
#                                   MIN_YEAR..MAX_YEAR, gy = 2000..MAX_YEAR, with
#                                   year and geoid_year columns. municipality and
#                                   county are as of y whatever gy is, so they are
#                                   kept only where gy == y (NA otherwise); that
#                                   keeps the file to about 300 KB, not 1.2 MB
#
# To export a tag that isn't pushed yet, set NJLEA_GIT to a local clone, e.g.
# NJLEA_GIT=../../njlea/njlea.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1 || length(args) > 3) {
  stop("Usage: Rscript scripts/export_data.R <git-ref> [out-dir] [expected-dir]")
}
ref <- args[[1]]
out_dir <- if (length(args) >= 2) args[[2]] else "data"
expected_dir <- if (length(args) >= 3) args[[3]] else file.path("tests", "parity", "expected")

tables <- c("agency", "agency_municipality", "agency_alias", "agency_ori", "alias_source")

lib <- file.path(tempdir(), "njlea-lib")
dir.create(lib, showWarnings = FALSE)
# Missing hard dependencies (njmunicipalities, from Remotes) are installed into
# lib too; installed ones are used as they are.
.libPaths(c(lib, .libPaths()))
local_git <- Sys.getenv("NJLEA_GIT")
if (nzchar(local_git)) {
  remotes::install_git(
    paste0("file://", normalizePath(local_git)),
    ref = ref, lib = lib, upgrade = "never", dependencies = NA, quiet = TRUE
  )
} else {
  remotes::install_github(
    "tor-gu/njlea",
    ref = ref, lib = lib, upgrade = "never", dependencies = NA, quiet = TRUE
  )
}
desc <- packageDescription("njlea", lib.loc = lib)
commit <- if (!is.null(desc$RemoteSha)) desc$RemoteSha else NA
mdesc <- packageDescription("njmunicipalities")
mcommit <- if (!is.null(mdesc$RemoteSha)) mdesc$RemoteSha else NA
min_year <- getFromNamespace("MIN_YEAR", "njlea")
max_year <- getFromNamespace("MAX_YEAR", "njlea")

column_type <- function(col) {
  if (inherits(col, "Date")) {
    "date"
  } else if (is.factor(col)) {
    "factor"
  } else if (is.logical(col)) {
    "logical"
  } else if (is.integer(col)) {
    "integer"
  } else if (is.numeric(col)) {
    if (any(!is.na(col) & col != round(col))) {
      stop("numeric column with non-integer values")
    }
    "integer"
  } else if (is.character(col)) {
    "character"
  } else {
    stop("unexpected column class ", class(col)[[1]])
  }
}

# Writes df as <name>.csv, and returns its columns.csv and levels.csv rows
export_table <- function(df, name) {
  df <- as.data.frame(df)
  types <- vapply(
    names(df),
    function(column) {
      tryCatch(column_type(df[[column]]), error = function(e) {
        stop(name, ".", column, ": ", conditionMessage(e))
      })
    },
    character(1)
  )
  levels_out <- list()
  for (column in names(df)) {
    col <- df[[column]]
    if (is.factor(col) && "" %in% levels(col)) {
      stop(name, ".", column, ": has an empty factor level")
    }
    if (is.character(col)) {
      empty <- which(!is.na(col) & col == "")
      if (length(empty) > 0) {
        message("Converted ", length(empty), " empty string(s) to NA in ", name, ".", column)
        col[empty] <- NA
        df[[column]] <- col
      }
    }
    if (types[[column]] == "integer" && !is.integer(col)) {
      df[[column]] <- as.integer(col)
    }
    if (is.factor(col)) {
      lv <- levels(col)
      levels_out[[length(levels_out) + 1]] <- data.frame(
        table = name, column = column, position = seq_along(lv), level = lv
      )
    }
  }
  write.csv(df, file.path(out_dir, paste0(name, ".csv")),
            row.names = FALSE, na = "", fileEncoding = "UTF-8")
  message("Wrote ", nrow(df), " rows to ", file.path(out_dir, paste0(name, ".csv")))
  list(
    columns = data.frame(table = name, position = seq_along(types),
                         column = names(df), type = types),
    levels = do.call(rbind, levels_out)
  )
}

# Writes df gzipped, with gzip -n so the same data gives the same bytes
write_csv_gz <- function(df, path) {
  csv <- sub("\\.gz$", "", path)
  write.csv(as.data.frame(df), csv, row.names = FALSE, na = "", fileEncoding = "UTF-8")
  unlink(path)
  status <- system2("gzip", c("-n", "-9", shQuote(csv)))
  if (status != 0) stop("gzip failed for ", csv)
  message("Wrote ", nrow(df), " rows to ", path)
}

dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(expected_dir, showWarnings = FALSE, recursive = TRUE)

exported <- list()
for (name in tables) {
  env <- new.env()
  data(list = name, package = "njlea", lib.loc = lib, envir = env)
  exported[[name]] <- export_table(env[[name]], name)
}
municipalities <- getFromNamespace("municipalities", "njmunicipalities")
exported[["municipalities"]] <- export_table(municipalities, "municipalities")

write.csv(do.call(rbind, lapply(exported, `[[`, "columns")),
          file.path(out_dir, "columns.csv"), row.names = FALSE, fileEncoding = "UTF-8")
write.csv(do.call(rbind, lapply(exported, `[[`, "levels")),
          file.path(out_dir, "levels.csv"), row.names = FALSE, fileEncoding = "UTF-8")

# R's results, for tests/parity
years <- min_year:max_year
agencies <- do.call(rbind, lapply(years, function(y) {
  cbind(year = y, as.data.frame(njlea::get_agencies(y)))
}))
write_csv_gz(agencies, file.path(expected_dir, "agencies.csv.gz"))
links <- do.call(rbind, lapply(years, function(y) {
  do.call(rbind, lapply(2000:max_year, function(gy) {
    m <- as.data.frame(njlea::get_agency_municipalities(y, geoid_year = gy))
    if (gy != y) {
      m$municipality <- NA_character_
      m$county <- NA_character_
    }
    cbind(year = y, geoid_year = gy, m)
  }))
}))
write_csv_gz(links, file.path(expected_dir, "agency_municipalities.csv.gz"))

source_lines <- c(
  "package=njlea",
  paste0("version=", desc$Version),
  paste0("ref=", ref),
  paste0("commit=", commit),
  paste0("njmunicipalities_version=", mdesc$Version),
  paste0("njmunicipalities_commit=", mcommit),
  paste0("min_year=", min_year),
  paste0("max_year=", max_year),
  paste0("exported=", format(Sys.Date()))
)
writeLines(source_lines, file.path(out_dir, "SOURCE"))
message("Wrote ", file.path(out_dir, "SOURCE"))
