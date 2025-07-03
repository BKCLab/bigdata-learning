while true; do
  # Generate a random product ID
  product_id=$(( RANDOM % 100 + 1 )) # IDs from 1 to 100

  # Generate a random blog post ID
  blog_post_id=$(( RANDOM % 50 + 1 )) # IDs from 1 to 50

  # Generate a random search query (simple example)
  search_query_options=("apple" "banana" "orange" "grape" "kiwi")
  random_search_query=${search_query_options[$(( RANDOM % ${#search_query_options[@]} ))]}

  path=$(shuf -n1 -e \
    / \
    /home \
    /login \
    /api/data \
    "/products?id=$product_id" \
    "/blog/post/$blog_post_id" \
    "/search?q=$random_search_query" \
    /dashboard \
    /settings \
    /profile \
    /about \
    /contact \
    "/users/$(( RANDOM % 20 + 1 ))" \
    "/items/$(( RANDOM % 500 + 1 ))" \
    "/categories/$(( RANDOM % 10 + 1 ))/products" \
    "/api/status" \
    "/reports/daily" \
    "/admin/logs")

  curl -s "http://localhost:80$path"
  sleep 1
done
