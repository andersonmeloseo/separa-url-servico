import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import pandas as pd

def get_urls_from_sitemap(sitemap_url, visited=None):
    if visited is None:
        visited = set()
    urls = []
    if sitemap_url in visited:
        return urls
    visited.add(sitemap_url)
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()
    except Exception as e:
        print(f"Erro ao acessar {sitemap_url}: {e}")
        return urls
    try:
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"Erro ao parsear XML de {sitemap_url}: {e}")
        return urls
    if root.tag.endswith("sitemapindex"):
        for sitemap in root.findall(".//{*}sitemap"):
            loc = sitemap.find("{*}loc")
            if loc is not None and loc.text:
                child_sitemap_url = loc.text.strip()
                urls.extend(get_urls_from_sitemap(child_sitemap_url, visited))
    elif root.tag.endswith("urlset"):
        for url in root.findall(".//{*}url"):
            loc = url.find("{*}loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    else:
        print(f"Formato desconhecido em {sitemap_url}")
    return urls

def process_url(url):
    parsed = urlparse(url)
    base = [parsed.scheme + "://"]
    netloc = parsed.netloc
    if netloc.startswith("www."):
        subdomain = "www"
        domain = netloc[4:]
    else:
        subdomain = ""
        domain = netloc
    base.extend([subdomain, domain])
    path_segments = [seg for seg in parsed.path.split("/") if seg]
    if not path_segments:
        head = []
        last = []
    else:
        if len(path_segments) == 1:
            head = []
            last = path_segments[0].split("-")
        else:
            head = path_segments[:-1]
            last = path_segments[-1].split("-")
    last = [part.capitalize() for part in last]
    return base, head, last

def extract_service_location(url):
    parsed = urlparse(url)
    path_segments = [seg for seg in parsed.path.split("/") if seg]
    # Padrão 1: se "services" estiver no caminho
    if "services" in path_segments:
        idx = path_segments.index("services")
        service = ""
        city = ""
        state = ""
        if len(path_segments) > idx + 1:
            service = path_segments[idx+1].replace("-", " ").strip().title()
        if len(path_segments) > idx + 2:
            token = path_segments[idx+2]
            parts = token.split("-")
            if len(parts) >= 2:
                city = " ".join(p.capitalize() for p in parts[:-1])
                state = parts[-1].upper()
            else:
                city = token.replace("-", " ").strip().title()
        return service, city, state
    else:
        if not path_segments:
            return "", "", ""
        last_segment = path_segments[-1]
        # Padrão 2: verifica se o último segmento contém "-in-"
        if "-in-" in last_segment:
            parts = last_segment.split("-in-")
            service = parts[0].replace("-", " ").strip().title()
            location_part = parts[1]
            location_tokens = location_part.split("-")
            if len(location_tokens) >= 2:
                city = " ".join(token.capitalize() for token in location_tokens[:-1])
                state = location_tokens[-1].upper()
            else:
                city = location_tokens[0].replace("-", " ").strip().title() if location_tokens else ""
                state = ""
            return service, city, state
        else:
            return "", "", ""

def create_segmented_urls_df(processed_data):
    max_head = max(len(head) for base, head, last in processed_data)
    max_nonfinal = max((len(last) - 1 if len(last) > 0 else 0) for base, head, last in processed_data)
    rows = []
    for base, head, last in processed_data:
        head_padded = head + [""] * (max_head - len(head))
        if last:
            if len(last) == 1:
                nonfinal = []
                final = last[0]
            else:
                nonfinal = last[:-1]
                final = last[-1]
            nonfinal_padded = nonfinal + [""] * (max_nonfinal - len(nonfinal))
            # Insere 6 colunas vazias entre as partes não finais e o último elemento
            last_block = nonfinal_padded + [""] * 6 + [final]
        else:
            last_block = [""] * (max_nonfinal + 6 + 1)
        row = base + head_padded + last_block
        rows.append(row)
    base_headers = ["Protocolo", "Subdomínio", "Domínio"]
    head_headers = [f"Caminho Segmento {i+1}" for i in range(max_head)]
    nonfinal_headers = [f"Último Segmento Parte {i+1}" for i in range(max_nonfinal)]
    espacos_headers = [f"Espaço Vazio {i+1}" for i in range(6)]
    final_header = ["Último Elemento da Última Trilha"]
    header = base_headers + head_headers + nonfinal_headers + espacos_headers + final_header
    return pd.DataFrame(rows, columns=header)

def create_service_location_df(urls):
    rows = []
    for url in urls:
        service, city, state = extract_service_location(url)
        row = [url, service, city] + [""] * 6 + [state]
        rows.append(row)
    columns = ["URL Completa", "Serviço", "Cidade", "Vazio 1", "Vazio 2", "Vazio 3", "Vazio 4", "Vazio 5", "Vazio 6", "Estado"]
    return pd.DataFrame(rows, columns=columns)

def write_excel_all(processed_data, urls, domain, output_filename=None):
    df_segmented = create_segmented_urls_df(processed_data)
    df_service_location = create_service_location_df(urls)
    if output_filename is None:
        output_filename = f"{domain}.xlsx"
    with pd.ExcelWriter(output_filename, engine="xlsxwriter") as writer:
        df_segmented.to_excel(writer, index=False, sheet_name="Segmented URLs")
        df_service_location.to_excel(writer, index=False, sheet_name="Serviço e Localização")
    print(f"Arquivo Excel gerado: {output_filename}")

def main():
    sitemaps_input = input("Cole as URLs dos sitemaps, separadas por vírgula:\n")
    sitemap_urls = [url.strip() for url in sitemaps_input.split(",") if url.strip()]
    if not sitemap_urls:
        print("Nenhuma URL de sitemap foi fornecida. Encerrando o programa.")
        return
    first_parsed = urlparse(sitemap_urls[0])
    netloc = first_parsed.netloc
    domain_for_filename = netloc[4:] if netloc.startswith("www.") else netloc
    all_urls = []
    for sitemap_url in sitemap_urls:
        print(f"Processando sitemap: {sitemap_url}")
        urls = get_urls_from_sitemap(sitemap_url)
        all_urls.extend(urls)
    all_urls = sorted(set(all_urls))
    print(f"Total de URLs encontradas: {len(all_urls)}")
    processed_data = [process_url(url) for url in all_urls]
    write_excel_all(processed_data, all_urls, domain_for_filename)

if __name__ == "__main__":
    main()
